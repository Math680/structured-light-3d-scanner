"""Lecture et ecriture d'images.

OpenCV lit parfois mal les chemins Windows contenant des accents. Les fonctions
ci-dessous contournent le probleme en passant par des tableaux d'octets.
"""

from pathlib import Path

import cv2
import numpy as np


def lire_image_gris(chemin: Path) -> np.ndarray:
    donnees = np.fromfile(str(chemin), dtype=np.uint8)
    image = cv2.imdecode(donnees, cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise FileNotFoundError(f"Image illisible : {chemin}")
    return image


def lire_image_couleur(chemin: Path) -> np.ndarray:
    donnees = np.fromfile(str(chemin), dtype=np.uint8)
    image = cv2.imdecode(donnees, cv2.IMREAD_COLOR)
    if image is None:
        raise FileNotFoundError(f"Image illisible : {chemin}")
    return image


def ecrire_image(chemin: Path, image: np.ndarray) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    succes, donnees = cv2.imencode(chemin.suffix, image)
    if not succes:
        raise RuntimeError(f"Impossible d'ecrire : {chemin}")
    donnees.tofile(str(chemin))

