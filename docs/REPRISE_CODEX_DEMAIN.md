# Notes de reprise

Le dépôt a été nettoyé pour ne garder que la version fonctionnelle.

## Chemins importants

- `reconstruction/` : pipeline Python propre.
- `UI/ProntoUI/` : interface Windows Forms.
- `tools/creer_masque.py` : outil interactif de création de masques.
- `reconstruction/calibration_validee/` : matrices `MR.txt` et `ME.txt`
  validées.

## Commandes utiles

```powershell
python tools\creer_masque.py --folder "reconstruction\captures\captures\1"
cd reconstruction
python scripts\lancer_reconstruction.py --objets "1" --ouvrir-html
```

## Données générées localement

Les captures et résultats sont volontairement ignorés par Git :

- `reconstruction/captures/`
- `reconstruction/resultats/`
- `UI/**/bin/`
- `UI/**/obj/`

Ces dossiers sont recréés par l'interface ou par les scripts.
