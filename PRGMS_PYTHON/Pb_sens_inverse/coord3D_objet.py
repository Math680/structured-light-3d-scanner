import numpy as np
import os
from skimage import io
import matplotlib.pyplot as plt
from scipy.interpolate import RegularGridInterpolator

class Coord3D:
    def __init__(self, ME, MR):
        self.ME = ME
        self.MR = MR

    def triangulate_vectorized(self, uE, vE, uR, vR):
        """Calcul 3D par moindres carrés (version rapide)"""
        n = uE.size
        A = np.zeros((n, 4, 3))
        b = np.zeros((n, 4))

        # Équations Émetteur
        A[:, 0, :] = uE[:, np.newaxis] * self.ME[2, :3] - self.ME[0, :3]
        A[:, 1, :] = vE[:, np.newaxis] * self.ME[2, :3] - self.ME[1, :3]
        b[:, 0] = self.ME[0, 3] - uE * self.ME[2, 3]
        b[:, 1] = self.ME[1, 3] - vE * self.ME[2, 3]

        # Équations Récepteur
        A[:, 2, :] = uR[:, np.newaxis] * self.MR[2, :3] - self.MR[0, :3]
        A[:, 3, :] = vR[:, np.newaxis] * self.MR[2, :3] - self.MR[1, :3]
        b[:, 2] = self.MR[0, 3] - uR * self.MR[2, 3]
        b[:, 3] = self.MR[1, 3] - vR * self.MR[2, 3]

        At = A.transpose(0, 2, 1)
        AtA = At @ A
        Atb = At @ b[..., np.newaxis]
        return np.linalg.solve(AtA, Atb).reshape(n, 3)

if __name__ == "__main__":
    # 1. Gestion des chemins
    script_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.abspath(os.path.join(script_dir, os.pardir, os.pardir))
    folder_stockage = os.path.join(parent_dir, "stockage")
    folder_img = os.path.join(parent_dir, "img")

    # 2. Chargement des données
    ME = np.loadtxt(os.path.join(folder_stockage, "ME.txt"))
    MR = np.loadtxt(os.path.join(folder_stockage, "MR.txt"))
    
    # Chargement sous forme de matrices (grids) pour vérifier les dimensions
    uE_grid = np.loadtxt(os.path.join(folder_stockage, "uE.txt"))
    vE_grid = np.loadtxt(os.path.join(folder_stockage, "vE.txt"))
    uR_grid = np.loadtxt(os.path.join(folder_stockage, "uRZoom.txt"))
    vR_grid = np.loadtxt(os.path.join(folder_stockage, "vRZoom.txt"))

    # Image d'intensité pour le masque
    img_path = os.path.join(folder_img, "IRZoom1.bmp")
    img_int = io.imread(img_path)
    int_R_grid = img_int[:,:,0] if img_int.ndim == 3 else img_int

    # 3. ALIGNEMENT DES DIMENSIONS (Interpollation)
    # Si l'émetteur n'a pas la même taille que le récepteur, on le redimensionne
    if uE_grid.shape != uR_grid.shape:
        print(f"Redimensionnement : Emetteur {uE_grid.shape} -> Récepteur {uR_grid.shape}")
        
        # On crée des fonctions d'interpolation pour uE et vE
        hE, wE = uE_grid.shape
        interp_uE = RegularGridInterpolator((np.arange(hE), np.arange(wE)), uE_grid, bounds_error=False, fill_value=0)
        interp_vE = RegularGridInterpolator((np.arange(hE), np.arange(wE)), vE_grid, bounds_error=False, fill_value=0)

        # On définit les points où on veut calculer uE/vE (la grille du récepteur)
        hR, wR = uR_grid.shape
        # On crée une grille normalisée ou proportionnelle (selon votre projet Pronto)
        # Note : Si uE.txt est la grille fixe, cette étape harmonise juste les tailles de vecteurs.
        rr, cc = np.meshgrid(np.linspace(0, hE-1, hR), np.linspace(0, wE-1, wR), indexing='ij')
        pts = np.column_stack((rr.ravel(), cc.ravel()))
        
        uE_aligned = interp_uE(pts).reshape(hR, wR)
        vE_aligned = interp_vE(pts).reshape(hR, wR)
    else:
        uE_aligned, vE_aligned = uE_grid, vE_grid

    # 4. Aplatissement et Masquage
    uE_v = uE_aligned.ravel()
    vE_v = vE_aligned.ravel()
    uR_v = uR_grid.ravel()
    vR_v = vR_grid.ravel()
    int_R_v = int_R_grid.ravel()

    # Création du masque (Points valides + Intensité suffisante)
    seuil = 20
    mask = (np.isfinite(uE_v)) & (np.isfinite(uR_v)) & (int_R_v > seuil)

    # 5. Reconstruction
    coord = Coord3D(ME, MR)
    XYZ = coord.triangulate_vectorized(uE_v[mask], vE_v[mask], uR_v[mask], vR_v[mask])

    # 6. Filtrage Z (on garde ce qui est devant la caméra)
    mask_z = (XYZ[:, 2] > 0) & (XYZ[:, 2] < 3000)
    XYZ_final = XYZ[mask_z]
    C_final = int_R_v[mask][mask_z]

    # 7. Affichage
    fig = plt.figure(figsize=(12, 5))
    ax1 = fig.add_subplot(121, projection='3d')
    ax1.scatter(XYZ_final[:,0], XYZ_final[:,1], XYZ_final[:,2], c=C_final, cmap='gray', s=1)
    ax1.set_title("Nuage 3D")
    
    ax2 = fig.add_subplot(122)
    sc = ax2.scatter(XYZ_final[:,0], XYZ_final[:,1], c=XYZ_final[:,2], cmap='jet', s=1)
    plt.colorbar(sc, label="Z (mm)")
    ax2.set_aspect('equal')
    ax2.set_title("Carte de profondeur")
    plt.show()