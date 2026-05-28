from __future__ import annotations

"""Images de controle sauvegardees pendant la reconstruction."""

import shutil
from pathlib import Path

import cv2
import numpy as np

from .chemins import DOSSIER_CALIBRATION
from .images import ecrire_image


def copier_diagnostics_calibration(dossier_resultats: Path) -> None:
    sortie = dossier_resultats / "diagnostics_calibration"
    sortie.mkdir(parents=True, exist_ok=True)
    for motif in ("*_controle.png", "*_points.txt", "resume_calibration.json", "resume_calibration_corrigee.json"):
        for chemin in DOSSIER_CALIBRATION.glob(motif):
            shutil.copy2(chemin, sortie / chemin.name)


def sauver_diagnostics_franges(
    dossier_sortie: Path,
    captures: np.ndarray,
    masque: np.ndarray,
    polygone: np.ndarray | None,
    code_projecteur: np.ndarray,
) -> None:
    dossier_diag = dossier_sortie / "diagnostics_franges"
    dossier_diag.mkdir(parents=True, exist_ok=True)

    valeurs = code_projecteur[masque]
    normalise = np.zeros_like(code_projecteur, dtype=np.uint8)
    if valeurs.size > 0 and valeurs.max() > valeurs.min():
        normalise[masque] = ((valeurs - valeurs.min()) * 255.0 / (valeurs.max() - valeurs.min())).astype(np.uint8)

    couleur_code = cv2.applyColorMap(normalise, cv2.COLORMAP_TURBO)
    couleur_code[~masque] = 0
    lignes = cv2.Canny(normalise, 40, 120)
    couleur_code[lignes > 0] = (0, 255, 0)
    if polygone is not None:
        cv2.polylines(couleur_code, [polygone], True, (255, 0, 255), 2, cv2.LINE_AA)
    ecrire_image(dossier_diag / "coordonnees_projecteur_et_lignes_franges.png", couleur_code)

    vignettes = []
    for indice, capture in enumerate(captures, start=1):
        image = cv2.cvtColor(capture, cv2.COLOR_GRAY2BGR)
        image[~masque] = 0
        cv2.putText(image, f"capture {indice}", (18, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        vignettes.append(cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA))

    lignes_montage = []
    for i in range(0, len(vignettes), 2):
        bloc = vignettes[i : i + 2]
        if len(bloc) == 1:
            bloc.append(np.zeros_like(vignettes[0]))
        lignes_montage.append(np.hstack(bloc))
    ecrire_image(dossier_diag / "captures_franges_utilisees.png", np.vstack(lignes_montage))
