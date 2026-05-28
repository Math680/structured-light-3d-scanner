# PRONTO - Imageur 3D

Prototype de reconstruction 3D par lumière structurée binaire.

Le projet pilote une caméra et un vidéoprojecteur, calibre le couple
caméra/projecteur, acquiert une séquence de franges binaires puis reconstruit un
nuage de points 3D visualisable dans un navigateur. La version actuelle inclut
aussi l'association d'une image couleur aux points reconstruits.

## Organisation du dépôt

```text
.
├── UI/ProntoUI/                 Interface Windows Forms C#
├── reconstruction/              Pipeline Python fonctionnel
│   ├── src/reconstruction3d/     Code Python principal
│   ├── scripts/                 Lanceurs reconstruction
│   ├── scripts_calibration/     Calibration caméra/projecteur
│   ├── scripts_projection/      Projection plein écran
│   └── calibration_validee/     Calibration validée MR/ME
├── tools/creer_masque.py        Outil interactif de création de masque
└── docs/                        Documents utiles du projet
```

Les anciens scripts expérimentaux, caches Python, sorties de tests, captures et
résultats générés ne sont pas conservés dans le dépôt.

## Prérequis

- Windows
- Python 3.7 ou plus récent
- Packages Python : `numpy`, `opencv-python`
- Visual Studio 2019/2022 avec MSBuild et .NET Framework 4.8
- NuGet pour restaurer les dépendances de l'interface

Installation Python minimale :

```powershell
python -m pip install -r requirements.txt
```

## Interface graphique

Restaurer les packages NuGet puis compiler :

```powershell
nuget restore UI\ProntoUI\ProntoUI.sln
msbuild UI\ProntoUI\ProntoUI.sln /p:Configuration=Debug /p:Platform="Any CPU"
```

L'exécutable généré se trouve ensuite dans :

```text
UI/ProntoUI/ProntoUI/bin/Debug/ProntoUI.exe
```

Depuis l'UI, les captures sont copiées dans `reconstruction/captures/captures`.
La calibration lance l'outil de masque puis
`reconstruction/scripts_calibration/ajuster_points_calibration.py`.
L'acquisition lance ensuite le masque objet puis
`reconstruction/scripts/lancer_reconstruction.py --objets "1" --ouvrir-html`.

## Utilisation du pipeline Python

Créer ou modifier un masque :

```powershell
python tools\creer_masque.py --folder "reconstruction\captures\captures\1"
```

Lancer une reconstruction :

```powershell
cd reconstruction
python scripts\lancer_reconstruction.py --objets "1" --ouvrir-html
```

Les résultats sont écrits dans :

```text
reconstruction/resultats/<nom_objet>/
```

Fichiers principaux produits :

- `vue_3d_interactive.html` : visualisation 3D dans le navigateur
- `points_3d_repere_plan.txt` : points 3D dans le repère du plan
- `points_3d_brut.txt` : points 3D avant changement de repère
- `couleurs_rgb.txt` : couleurs associées aux points si `capture_couleur.png`
  est disponible

## Données générées

Les dossiers suivants sont volontairement ignorés par Git :

- `reconstruction/captures/`
- `reconstruction/resultats/`
- `UI/**/bin/`
- `UI/**/obj/`

Ils peuvent être recréés par l'interface ou par les scripts Python.
