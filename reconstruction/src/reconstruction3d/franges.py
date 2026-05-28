"""Decodage des franges projetees.

Les captures contiennent une suite de franges noires/blanches. Le but de ce
module est de convertir ces images en une coordonnee horizontale du projecteur.
"""

from pathlib import Path

import cv2
import numpy as np

from .images import lire_image_gris


def compter_captures_utilisables(dossier_capture: Path) -> int:
    """Compte les captures consecutives depuis capture_1.png, en s'arretant a 7.

    La huitieme image a ete gardee hors du pipeline final car elle est moins
    fiable sur les essais realises.
    """
    nombre = 0
    for indice in range(1, 8):
        if (dossier_capture / f"capture_{indice}.png").exists():
            nombre = indice
        else:
            break
    if nombre == 0:
        raise FileNotFoundError(f"Aucune capture trouvee dans {dossier_capture}")
    return nombre


def charger_captures(dossier_capture: Path, nombre_captures: int) -> np.ndarray:
    images = [lire_image_gris(dossier_capture / f"capture_{indice}.png") for indice in range(1, nombre_captures + 1)]
    return np.stack(images, axis=0)


def binariser_franges(captures: np.ndarray, masque: np.ndarray) -> np.ndarray:
    """Transforme les images de franges en images binaires 0/1.

    Le seuil est calcule pixel par pixel a partir du minimum et du maximum vus
    pendant la sequence.
    """
    image_max = captures.max(axis=0).astype(np.float32)
    image_min = captures.min(axis=0).astype(np.float32)
    seuil = (image_max + image_min) * 0.5
    binaire = (captures.astype(np.float32) > seuil[None, :, :]).astype(np.uint8)
    binaire[:, ~masque] = 0
    return binaire


def decoder_coordonnees_projecteur(franges_binaires: np.ndarray, masque: np.ndarray) -> np.ndarray:
    """Calcule le code projecteur de chaque pixel.

    Dans le generateur, une bande blanche correspond a un indice pair, donc au
    chiffre binaire 0. On inverse donc les bits avant de calculer le code.
    """
    franges_inversees = 1 - franges_binaires
    nombre_bits = franges_inversees.shape[0]
    poids = (2 ** np.arange(nombre_bits - 1, -1, -1)).astype(np.int32)[:, None, None]
    code = np.sum(franges_inversees * poids, axis=0)
    code[~masque] = 0
    code = cv2.medianBlur(code.astype(np.uint16), 3).astype(np.float32)
    code[~masque] = 0
    return code


def masque_objet_depuis_franges(captures: np.ndarray, masque: np.ndarray) -> np.ndarray:
    image_max = captures.max(axis=0)
    image_min = captures.min(axis=0)
    contraste = image_max.astype(np.int16) - image_min.astype(np.int16)
    return masque & (contraste > 20) & (image_max > 35)

