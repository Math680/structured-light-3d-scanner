import json
import os
import argparse
import re
from pathlib import Path
import cv2
import numpy as np


def numero_capture(path):
    match = re.fullmatch(r"capture_(\d+)\.png", path.name, re.IGNORECASE)
    return int(match.group(1)) if match else None


def lire_image(path):
    with open(path, 'rb') as f:
        bytes_data = np.frombuffer(f.read(), dtype=np.uint8)
        return cv2.imdecode(bytes_data, cv2.IMREAD_COLOR)


def choisir_image_reference(target_folder):
    captures_numeriques = []
    for path in target_folder.glob("capture_*.png"):
        numero = numero_capture(path)
        if numero is not None:
            captures_numeriques.append((numero, path))
    captures_numeriques.sort()

    nom_dossier = target_folder.name.lower()
    est_calibration = nom_dossier in ("calibration_recepteur", "calibration_emetteur")
    if est_calibration:
        images_calibration = [path for _, path in captures_numeriques]
        if len(images_calibration) < 2:
            images_calibration = sorted(
                list(target_folder.glob("*.png"))
                + list(target_folder.glob("*.jpg"))
                + list(target_folder.glob("*.bmp"))
            )
        if len(images_calibration) < 2:
            return (lire_image(images_calibration[0]), images_calibration[0].name) if images_calibration else (None, None)

        img1 = lire_image(images_calibration[0])
        img2 = lire_image(images_calibration[-1])
        if img1 is not None and img2 is not None:
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)
            nom = images_calibration[0].name + " + " + images_calibration[-1].name
            return cv2.addWeighted(img1, 0.5, img2, 0.5, 0), nom

    if captures_numeriques:
        ref_path = captures_numeriques[-1][1]
        return lire_image(ref_path), ref_path.name

    images = sorted(
        list(target_folder.glob("*.png"))
        + list(target_folder.glob("*.jpg"))
        + list(target_folder.glob("*.bmp"))
    )
    if not images:
        return None, None
    ref_path = images[-1]
    return lire_image(ref_path), ref_path.name


def main():
    parser = argparse.ArgumentParser(description="Cree ou modifie un masque de capture.")
    parser.add_argument("--folder", help="Dossier de captures a ouvrir directement.")
    args = parser.parse_args()

    print("==================================================")
    print("    Outil Interactif de Création de Masque       ")
    print("==================================================")
    
    # Trouver la racine du projet
    workspace_root = Path(__file__).resolve().parents[1]
    target_folder = Path(args.folder).resolve() if args.folder else None
    
    # Lister les répertoires de captures potentiels
    search_dirs = [
        workspace_root / "reconstruction" / "captures" / "captures",
    ]
    
    candidate_folders = []
    for s_dir in search_dirs:
        if s_dir.exists():
            for child in s_dir.iterdir():
                if child.is_dir():
                    # Vérifier s'il contient des images
                    images = list(child.glob("*.png")) + list(child.glob("*.jpg")) + list(child.glob("*.bmp"))
                    if images:
                        candidate_folders.append(child)
                        
    # Supprimer les doublons éventuels basés sur le chemin absolu
    unique_folders = []
    seen = set()
    for folder in candidate_folders:
        abs_path = str(folder.resolve())
        if abs_path not in seen:
            seen.add(abs_path)
            unique_folders.append(folder)

    if target_folder is not None:
        if not target_folder.exists() or not target_folder.is_dir():
            print(f"Dossier introuvable : {target_folder}")
            return
        unique_folders = [target_folder]
            
    if not unique_folders:
        print("Aucun dossier de captures trouvé.")
        return
        
    print("\nDossiers de captures disponibles :")
    for idx, folder in enumerate(unique_folders, 1):
        # Afficher le chemin relatif ou le nom pour plus de clarté
        try:
            rel = folder.relative_to(workspace_root)
        except ValueError:
            rel = folder.name
        has_mask = (folder / "mask_config.json").exists()
        mask_status = "[Masque existant]" if has_mask else "[Pas de masque]"
        print(f"  {idx}. {rel} {mask_status}")
        
    choice = "1" if target_folder is not None else input("\nSélectionnez un dossier (numéro) : ").strip()
    try:
        chosen_idx = int(choice) - 1
        if chosen_idx < 0 or chosen_idx >= len(unique_folders):
            print("Choix invalide.")
            return
        target_folder = unique_folders[chosen_idx]
    except ValueError:
        print("Entrée invalide.")
        return
        
    print(f"\nDossier sélectionné : {target_folder}")
    
    # Trouver une image de référence pour dessiner le masque
    img, ref_name = choisir_image_reference(target_folder)
    if img is None:
        print("Aucune image trouvée dans ce dossier.")
        return
        
    # Charger la dernière capture ou capture_1 de préférence
    print(f"Chargement de l'image de référence : {ref_name}")
    
    # Lecture OpenCV compatible avec les accents/chemins Windows longs
    # Image deja chargee par choisir_image_reference().
        
    if img is None:
        print("Erreur de chargement de l'image.")
        return
        
    # Variables pour stocker les points du polygone
    points = []
    
    # Charger un masque existant s'il y en a un
    mask_path = target_folder / "mask_config.json"
    if mask_path.exists():
        try:
            config = json.loads(mask_path.read_text(encoding="utf-8"))
            points = [list(pt) for pt in config.get("points", [])]
            print(f"Masque existant chargé avec {len(points)} points.")
        except Exception as e:
            print(f"Erreur de chargement du masque existant: {e}")
            
    # Fenêtre interactive
    window_name = "Selection du Masque - Pronto"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)
    
    def redraw():
        canvas = img.copy()
        # Dessiner le polygone actuel
        if len(points) > 0:
            for i in range(len(points)):
                cv2.circle(canvas, tuple(points[i]), 6, (0, 0, 255), -1)
                cv2.circle(canvas, tuple(points[i]), 8, (255, 255, 255), 1)
                cv2.putText(canvas, str(i+1), (points[i][0] + 10, points[i][1] - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA)
            if len(points) >= 2:
                pts_array = np.array(points, dtype=np.int32)
                cv2.polylines(canvas, [pts_array], True, (0, 255, 0), 2, cv2.LINE_AA)
                
                # Remplir le polygone avec une transparence verte
                overlay = canvas.copy()
                cv2.fillPoly(overlay, [pts_array], (0, 255, 0))
                cv2.addWeighted(overlay, 0.3, canvas, 0.7, 0, canvas)
                
        # Ajouter du texte d'aide
        cv2.rectangle(canvas, (0, 0), (canvas.shape[1], 60), (0, 0, 0), -1)
        cv2.putText(canvas, "Clic gauche: Ajouter point | Retour arriere (Back): Annuler point | C: Effacer tout", 
                    (15, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(canvas, "S: Sauvegarder et quitter | Q ou Echap: Quitter sans sauvegarder", 
                    (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
                    
        cv2.imshow(window_name, canvas)

    def mouse_callback(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            points.append([x, y])
            redraw()
            
    cv2.setMouseCallback(window_name, mouse_callback)
    redraw()
    
    while True:
        key = cv2.waitKey(20) & 0xFF
        if key == ord('q') or key == 27:  # 'q' ou Echap
            print("Fermeture sans sauvegarder.")
            break
        elif key == ord('s') or key == 13:  # 's' ou Entrée
            if len(points) < 3:
                print("Un masque nécessite au moins 3 points.")
                continue
            # Sauvegarder dans mask_config.json
            mask_data = {"points": points}
            mask_path.write_text(json.dumps(mask_data, indent=4), encoding="utf-8")
            print(f"\nMasque sauvegardé avec succès dans : {mask_path}")
            break
        elif key == ord('c'):  # 'c'
            points.clear()
            print("Points effacés.")
            redraw()
        elif key == 8 or key == ord('u'):  # Retour arrière ou 'u'
            if points:
                points.pop()
                print("Dernier point annulé.")
                redraw()
                
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
