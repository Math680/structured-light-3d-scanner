from __future__ import annotations

"""Gestion des masques.

Un masque est un quadrilatere qui indique la zone utile de l'image. Les pixels
en dehors du masque sont ignores. Pour les objets sans masque propre, on reprend
le masque du plan.
"""

import json
from pathlib import Path

import cv2
import numpy as np

from .chemins import DOSSIER_CAPTURES


def charger_masque(dossier_capture: Path, forme_image: tuple[int, int]) -> tuple[np.ndarray, np.ndarray | None]:
    chemin_masque = dossier_capture / "mask_config.json"
    if not chemin_masque.exists() and dossier_capture.name not in {"calibration_emetteur", "calibration_recepteur"}:
        chemin_plan = DOSSIER_CAPTURES / "plan" / "mask_config.json"
        if chemin_plan.exists():
            chemin_masque = chemin_plan

    if not chemin_masque.exists():
        return np.ones(forme_image, dtype=bool), None

    config = json.loads(chemin_masque.read_text(encoding="utf-8"))
    polygone = np.array(config["points"], dtype=np.int32)
    masque = np.zeros(forme_image, dtype=np.uint8)
    cv2.fillPoly(masque, [polygone], 255)
    return masque > 0, polygone


def appliquer_masque(captures: np.ndarray, masque: np.ndarray) -> np.ndarray:
    captures_masquees = captures.copy()
    captures_masquees[:, ~masque] = 0
    return captures_masquees
