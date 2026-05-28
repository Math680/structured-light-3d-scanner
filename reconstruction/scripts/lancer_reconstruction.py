"""Lanceur simple de la reconstruction 3D.

La logique est separee dans le dossier `src/reconstruction3d` pour que
l'architecture du code soit plus facile a lire et a presenter.
"""

from pathlib import Path
import sys


DOSSIER_PROJET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOSSIER_PROJET / "src"))

from reconstruction3d.cli import main


if __name__ == "__main__":
    main()

