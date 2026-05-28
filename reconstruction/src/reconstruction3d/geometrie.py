from __future__ import annotations

"""Calculs geometriques : triangulation, plan et changement de repere."""

import numpy as np


def trianguler(
    code_projecteur: np.ndarray,
    masque_objet: np.ndarray,
    matrice_recepteur: np.ndarray,
    matrice_emetteur: np.ndarray,
    pas_projecteur: float,
    retourner_pixels: bool = False,
) -> np.ndarray:
    hauteur, largeur = code_projecteur.shape
    lignes, colonnes = np.indices((hauteur, largeur), dtype=np.float64)
    valide = masque_objet

    u_recepteur = colonnes[valide]
    v_recepteur = lignes[valide]
    x_projecteur = (code_projecteur[valide] + 0.5) * pas_projecteur

    nombre_points = len(u_recepteur)
    if nombre_points == 0:
        raise RuntimeError("Aucun point valide trouve pour la reconstruction.")

    systeme = np.zeros((nombre_points, 3, 3), dtype=np.float64)
    second_membre = np.zeros((nombre_points, 3), dtype=np.float64)

    systeme[:, 0, :] = u_recepteur[:, None] * matrice_recepteur[2, :3] - matrice_recepteur[0, :3]
    systeme[:, 1, :] = v_recepteur[:, None] * matrice_recepteur[2, :3] - matrice_recepteur[1, :3]
    systeme[:, 2, :] = x_projecteur[:, None] * matrice_emetteur[2, :3] - matrice_emetteur[0, :3]

    second_membre[:, 0] = matrice_recepteur[0, 3] - u_recepteur * matrice_recepteur[2, 3]
    second_membre[:, 1] = matrice_recepteur[1, 3] - v_recepteur * matrice_recepteur[2, 3]
    second_membre[:, 2] = matrice_emetteur[0, 3] - x_projecteur * matrice_emetteur[2, 3]

    points = np.linalg.solve(systeme, second_membre[..., None]).reshape(nombre_points, 3)
    points_finis = np.isfinite(points).all(axis=1)
    points = points[points_finis]
    if retourner_pixels:
        pixels = np.column_stack([u_recepteur, v_recepteur]).astype(np.int32)[points_finis]
        return points, pixels
    return points


def ajuster_plan(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    centre = points.mean(axis=0)
    _, _, axes = np.linalg.svd(points - centre, full_matrices=False)
    distances = (points - centre) @ axes[-1]
    return centre, axes, distances


def filtrer_plan(points: np.ndarray) -> np.ndarray:
    z_mediane = np.median(points[:, 2])
    points = points[np.abs(points[:, 2] - z_mediane) <= 300.0]
    for _ in range(2):
        _, _, distances = ajuster_plan(points)
        seuil = np.percentile(np.abs(distances), 90)
        points = points[np.abs(distances) <= seuil]
    return points


def filtrer_objet(points: np.ndarray) -> np.ndarray:
    z_min, z_max = np.percentile(points[:, 2], [1, 99])
    return points[(points[:, 2] >= z_min) & (points[:, 2] <= z_max)]


def passer_dans_repere_plan(points: np.ndarray, centre_plan: np.ndarray, axes_plan: np.ndarray) -> np.ndarray:
    relatif = points - centre_plan
    axe_x = axes_plan[0]
    axe_y = axes_plan[1]
    axe_z = axes_plan[2]
    if axe_z[2] < 0:
        axe_z = -axe_z
    points_repere = np.column_stack([relatif @ axe_x, relatif @ axe_y, relatif @ axe_z])
    points_repere[:, 0] *= -1.0
    return points_repere
