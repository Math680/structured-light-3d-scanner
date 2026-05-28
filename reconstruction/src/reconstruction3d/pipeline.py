from __future__ import annotations

"""Orchestration de la reconstruction.

Ce module assemble les briques simples : lecture des captures, masques,
decodage des franges, triangulation, filtrage et sauvegarde des resultats.
"""

import json
from pathlib import Path

import numpy as np

from .chemins import DOSSIER_CAPTURES, DOSSIER_CALIBRATION, DOSSIER_RESULTATS, LARGEUR_PROJECTEUR_PX
from .diagnostics import sauver_diagnostics_franges
from .franges import (
    binariser_franges,
    charger_captures,
    compter_captures_utilisables,
    decoder_coordonnees_projecteur,
    masque_objet_depuis_franges,
)
from .geometrie import ajuster_plan, filtrer_objet, filtrer_plan, passer_dans_repere_plan, trianguler
from .images import lire_image_couleur
from .masques import appliquer_masque, charger_masque
from .visualisation import sauver_html_3d


def nettoyer_nom(nom: str) -> str:
    return nom.replace(" ", "_").replace("é", "e").replace("è", "e").replace("à", "a")


def charger_matrices_calibration() -> tuple[np.ndarray, np.ndarray]:
    chemin_mr = DOSSIER_CALIBRATION / "MR.txt"
    chemin_me = DOSSIER_CALIBRATION / "ME.txt"
    if not chemin_mr.exists():
        chemin_mr = DOSSIER_CALIBRATION / "MR_corrige.txt"
    if not chemin_me.exists():
        chemin_me = DOSSIER_CALIBRATION / "ME_corrige.txt"
    recepteur = np.loadtxt(chemin_mr)
    emetteur = np.loadtxt(chemin_me)
    return recepteur, emetteur


def filtrer_plan_avec_indices(points: np.ndarray) -> np.ndarray:
    indices = np.arange(len(points))
    z_mediane = np.median(points[:, 2])
    garder = np.abs(points[:, 2] - z_mediane) <= 300.0
    points = points[garder]
    indices = indices[garder]
    for _ in range(2):
        _, _, distances = ajuster_plan(points)
        seuil = np.percentile(np.abs(distances), 90)
        garder = np.abs(distances) <= seuil
        points = points[garder]
        indices = indices[garder]
    return indices


def filtrer_objet_avec_indices(points: np.ndarray) -> np.ndarray:
    z_min, z_max = np.percentile(points[:, 2], [1, 99])
    return np.flatnonzero((points[:, 2] >= z_min) & (points[:, 2] <= z_max))


def couleurs_depuis_capture(dossier_capture: Path, pixels: np.ndarray, forme_image: tuple[int, int]) -> np.ndarray | None:
    chemin_couleur = dossier_capture / "capture_couleur.png"
    if not chemin_couleur.exists():
        return None
    image = lire_image_couleur(chemin_couleur)
    hauteur, largeur = forme_image
    if image.shape[:2] != (hauteur, largeur):
        import cv2

        image = cv2.resize(image, (largeur, hauteur), interpolation=cv2.INTER_AREA)

    u = np.clip(pixels[:, 0], 0, largeur - 1)
    v = np.clip(pixels[:, 1], 0, hauteur - 1)
    couleurs_bgr = image[v, u]
    return couleurs_bgr[:, ::-1]


def reconstruire_un_dossier(
    nom_objet: str,
    matrice_recepteur: np.ndarray,
    matrice_emetteur: np.ndarray,
    centre_plan: np.ndarray | None,
    axes_plan: np.ndarray | None,
    filtrer_sous_plan: bool,
    tolerance_sous_plan: float,
) -> dict:
    dossier_capture = DOSSIER_CAPTURES / nom_objet
    nombre_captures = compter_captures_utilisables(dossier_capture)
    captures = charger_captures(dossier_capture, nombre_captures)
    masque, polygone = charger_masque(dossier_capture, captures[0].shape)
    captures = appliquer_masque(captures, masque)

    franges_binaires = binariser_franges(captures, masque)
    code_projecteur = decoder_coordonnees_projecteur(franges_binaires, masque)
    masque_objet = masque_objet_depuis_franges(captures, masque)
    pas_projecteur = LARGEUR_PROJECTEUR_PX / float(2**nombre_captures)

    points, pixels = trianguler(
        code_projecteur,
        masque_objet,
        matrice_recepteur,
        matrice_emetteur,
        pas_projecteur,
        retourner_pixels=True,
    )
    mode_plan = nom_objet.lower() == "plan"
    indices_filtres = filtrer_plan_avec_indices(points) if mode_plan else filtrer_objet_avec_indices(points)
    points = points[indices_filtres]
    pixels = pixels[indices_filtres]

    points_affiches = points
    if centre_plan is not None and axes_plan is not None:
        points_affiches = passer_dans_repere_plan(points, centre_plan, axes_plan)
        if not mode_plan and filtrer_sous_plan:
            garder = points_affiches[:, 2] >= -tolerance_sous_plan
            points = points[garder]
            points_affiches = points_affiches[garder]
            pixels = pixels[garder]

    centre, axes, distances = ajuster_plan(points)
    dossier_sortie = DOSSIER_RESULTATS / nettoyer_nom(nom_objet)
    dossier_sortie.mkdir(parents=True, exist_ok=True)

    np.savetxt(dossier_sortie / "points_3d_brut.txt", points, fmt="%.6f")
    np.savetxt(dossier_sortie / "points_3d_repere_plan.txt", points_affiches, fmt="%.6f")
    couleurs = couleurs_depuis_capture(dossier_capture, pixels, captures[0].shape)
    if couleurs is not None:
        np.savetxt(dossier_sortie / "couleurs_rgb.txt", couleurs, fmt="%d")
    sauver_diagnostics_franges(dossier_sortie, captures, masque, polygone, code_projecteur)
    sauver_html_3d(dossier_sortie / "vue_3d_interactive.html", nom_objet, points_affiches, couleurs)

    resume = {
        "objet": nom_objet,
        "captures_utilisees": nombre_captures,
        "pas_projecteur_px": pas_projecteur,
        "points": int(len(points)),
        "couleurs_depuis_capture": bool(couleurs is not None),
        "filtre_sous_plan": bool((not mode_plan) and filtrer_sous_plan),
        "tolerance_sous_plan_mm": tolerance_sous_plan,
        "centre_plan_ajuste": centre.tolist(),
        "normale_plan_ajuste": axes[-1].tolist(),
        "erreur_plan_rmse_mm": float(np.sqrt(np.mean(distances**2))),
        "erreur_plan_p95_mm": float(np.percentile(np.abs(distances), 95)),
    }
    (dossier_sortie / "resume.json").write_text(json.dumps(resume, indent=2), encoding="utf-8")
    return resume


def reconstruire_liste_objets(objets: list[str], filtrer_sous_plan: bool, tolerance_sous_plan: float) -> list[dict]:
    matrice_recepteur, matrice_emetteur = charger_matrices_calibration()
    DOSSIER_RESULTATS.mkdir(parents=True, exist_ok=True)

    resume_plan = reconstruire_un_dossier(
        "plan",
        matrice_recepteur,
        matrice_emetteur,
        centre_plan=None,
        axes_plan=None,
        filtrer_sous_plan=False,
        tolerance_sous_plan=tolerance_sous_plan,
    )

    points_plan = np.loadtxt(DOSSIER_RESULTATS / nettoyer_nom("plan") / "points_3d_brut.txt")
    centre_plan, axes_plan, _ = ajuster_plan(points_plan)
    points_plan_repere = passer_dans_repere_plan(points_plan, centre_plan, axes_plan)
    dossier_plan = DOSSIER_RESULTATS / nettoyer_nom("plan")
    np.savetxt(dossier_plan / "points_3d_repere_plan.txt", points_plan_repere, fmt="%.6f")
    sauver_html_3d(dossier_plan / "vue_3d_interactive.html", "plan", points_plan_repere)

    resumes = [resume_plan]
    for nom_objet in objets:
        if nom_objet.lower() == "plan":
            continue
        resumes.append(
            reconstruire_un_dossier(
                nom_objet,
                matrice_recepteur,
                matrice_emetteur,
                centre_plan=centre_plan,
                axes_plan=axes_plan,
                filtrer_sous_plan=filtrer_sous_plan,
                tolerance_sous_plan=tolerance_sous_plan,
            )
        )

    (DOSSIER_RESULTATS / "resume_global.json").write_text(json.dumps(resumes, indent=2), encoding="utf-8")
    return resumes
