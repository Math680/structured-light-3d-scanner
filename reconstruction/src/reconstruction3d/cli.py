"""Commande principale du projet."""

import argparse
import os

from .chemins import DOSSIER_RESULTATS, OBJETS_PAR_DEFAUT, TOLERANCE_SOUS_PLAN_MM
from .diagnostics import copier_diagnostics_calibration
from .pipeline import nettoyer_nom, reconstruire_liste_objets


def lire_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reconstruit les objets 3D a partir des captures.")
    parser.add_argument("--objets", nargs="+", default=OBJETS_PAR_DEFAUT, help="Objets a reconstruire.")
    parser.add_argument(
        "--garder-points-derriere-plan",
        action="store_true",
        help="Desactive le filtre qui retire les points situes sous le plan.",
    )
    parser.add_argument(
        "--tolerance-sous-plan",
        type=float,
        default=TOLERANCE_SOUS_PLAN_MM,
        help="Tolerance en mm sous le plan.",
    )
    parser.add_argument("--ouvrir-html", action="store_true", help="Ouvre les vues HTML apres reconstruction.")
    return parser.parse_args()


def main() -> None:
    args = lire_arguments()
    copier_diagnostics_calibration(DOSSIER_RESULTATS)
    resumes = reconstruire_liste_objets(
        objets=args.objets,
        filtrer_sous_plan=not args.garder_points_derriere_plan,
        tolerance_sous_plan=args.tolerance_sous_plan,
    )

    if args.ouvrir_html:
        for resume in resumes:
            os.startfile(DOSSIER_RESULTATS / nettoyer_nom(resume["objet"]) / "vue_3d_interactive.html")

    print("Reconstructions terminees.")
    print(f"Resultats : {DOSSIER_RESULTATS}")

