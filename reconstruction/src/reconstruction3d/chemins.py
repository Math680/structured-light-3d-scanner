"""Chemins communs du projet.

Tous les autres fichiers Python passent par ce module pour retrouver les
dossiers importants. Cela evite d'avoir des chemins ecrits un peu partout.
"""

from pathlib import Path


DOSSIER_PROJET = Path(__file__).resolve().parents[2]
DOSSIER_CAPTURES = DOSSIER_PROJET / "captures" / "captures"
DOSSIER_CALIBRATION = DOSSIER_PROJET / "calibration_validee"
DOSSIER_RESULTATS = DOSSIER_PROJET / "resultats"

OBJETS_PAR_DEFAUT = ["plan", "pyramide a plat", "Bras", "Sac Zainab", "Mines"]
LARGEUR_PROJECTEUR_PX = 1280.0
TOLERANCE_SOUS_PLAN_MM = 5.0

