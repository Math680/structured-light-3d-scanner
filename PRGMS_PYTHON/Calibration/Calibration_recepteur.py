import numpy as np
import cv2

def extraire_centroides(image_path, nb_points=21):
    img = cv2.imread(image_path)
    if img is None: return []

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Masques rouges
    lower_red1, upper_red1 = np.array([0, 100, 100]), np.array([10, 255, 255])
    lower_red2, upper_red2 = np.array([160, 100, 100]), np.array([180, 255, 255])
    mask = cv2.addWeighted(cv2.inRange(hsv, lower_red1, upper_red1), 1.0, 
                           cv2.inRange(hsv, lower_red2, upper_red2), 1.0, 0)

    # Nettoyage morphologique
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3,3), np.uint8))

    # Détection des clusters
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)

    # 1. On récupère tous les centroïdes (sauf le fond)
    tous_les_centroides = centroids[1:]
    
    # 2. FILTRAGE DES POINTS TROP PROCHES
    # On définit un rayon de sécurité (ex: 20 pixels). 
    # Si deux détections sont plus proches que ça, c'est la même pastille.
    rayon_securite = 20 
    points_filtres = []

    if len(tous_les_centroides) > 0:
        # On trie par aire (stats) pour garder le "vrai" centre si possible, 
        # ou simplement on parcourt
        for c in tous_les_centroides:
            est_trop_proche = False
            for pf in points_filtres:
                dist = np.linalg.norm(c - pf)
                if dist < rayon_securite:
                    est_trop_proche = True
                    break
            
            if not est_trop_proche:
                points_filtres.append(c)

    points_filtres = np.array(points_filtres)

    # 3. Tri final (Y puis X) pour correspondre à ton tableau M_points_3d
    # Note : Le tri est crucial pour que le point en haut à gauche soit bien le premier.
    points_filtres = points_filtres[points_filtres[:, 1].argsort()]
    
    if len(points_filtres) < nb_points:
        print(f"ALERTE : Seulement {len(points_filtres)} points trouvés après filtrage !")

    return points_filtres[:nb_points]

def calculer_MRN(points_3d, points_2d):
    """
    Résout BR.x = c (Eq. 30 et 31)
    """
    n = len(points_3d)
    B = np.zeros((2 * n, 11))
    c = np.zeros((2 * n, 1))

    for i in range(n):
        Xi, Yi, Zi = points_3d[i]
        ui, vi = points_2d[i]
        
        B[2*i]   = [Xi, Yi, Zi, 1, 0, 0, 0, 0, -ui*Xi, -ui*Yi, -ui*Zi]
        c[2*i]   = ui
        B[2*i+1] = [0, 0, 0, 0, Xi, Yi, Zi, 1, -vi*Xi, -vi*Yi, -vi*Zi]
        c[2*i+1] = vi

    # Résolution par pseudo-inverse : x = (Bt.B)^-1.Bt.c
    Bt = B.T
    xR = np.linalg.pinv(Bt @ B) @ Bt @ c
    
    # Reconstruction de la matrice 3x4 (m34 = 1)
    MRN = np.append(xR, [1.0]).reshape(3, 4)
    return MRN

def analyser_physique(MRN):
    # 1. Calcul de t3R à partir de la norme de la 3ème ligne (m3R)
    # Dans MR = t3R * MRN, on a m3R_physique = t3R * m3R_norm.
    # Comme ||m3R_physique|| doit être égal à 1 (vecteur r3 de rotation),
    # alors t3R = 1 / ||m3R_norm||
    m3R_norm = MRN[2, :3]
    t3R_calcule = 1.0 / np.linalg.norm(m3R_norm)
    
    # 2. Calcul de la matrice physique MR
    MR = t3R_calcule * MRN

    # 3. Extraction des vecteurs lignes de la matrice PHYSIQUE MR
    m1R, m2R, m3R = MR[0, :3], MR[1, :3], MR[2, :3]
    m14R, m24R, m34R = MR[0, 3], MR[1, 3], MR[2, 3]

    # 4. Paramètres intrinsèques (Eq. 28)
    u0R = np.dot(m1R, m3R)
    v0R = np.dot(m2R, m3R)
    alpha_uR = -np.linalg.norm(np.cross(m1R, m3R))
    alpha_vR = np.linalg.norm(np.cross(m2R, m3R))

    # 5. Matrice de rotation RR (Extrinsèques)
    r1R = (1 / alpha_uR) * (m1R - u0R * m3R)
    r2R = (1 / alpha_vR) * (m2R - v0R * m3R)
    r3R = m3R # Déjà de norme 1 grâce au calcul de t3R
    RR = np.vstack([r1R, r2R, r3R])

    # 6. Angles d'Euler (Degrés)
    theta = np.degrees(np.arcsin(-RR[2, 0]))
    psi = np.degrees(np.arctan2(RR[2, 1], RR[2, 2]))
    phi = np.degrees(np.arctan2(RR[1, 0], RR[0, 0]))
    
    # Sauvegarde des angles
    np.savetxt('Pronto-Imageur-3D/stockage/angles_exp.txt', (phi, theta, psi), fmt='%1.16e')
    # Sauvegarde de la matrice MR physique
    np.savetxt('Pronto-Imageur-3D/stockage/MR_physique.txt', MR, fmt='%1.16e')
    
    return MR, t3R_calcule, (u0R, v0R, alpha_uR, alpha_vR), (phi, theta, psi)
# --- EXÉCUTION ---

# 1. Vos points Mi (Xi, Yi, Zi) de l'image manuscrite
M_points_3d = np.array([
    [-0.47, 0.20625, 0], [-0.47, 0.06875, 0], [-0.47, -0.06875, 0], [-0.47, -0.20625, 0],
    [-0.276, 0.20625, 0], [-0.276, 0.06875, 0], [-0.276, -0.06875, 0], [-0.276, -0.20625, 0],
    [-0.092, 0.20625, 0], [-0.092, 0.06875, 0], [-0.092, -0.06875, 0], [-0.092, -0.20625, 0],
    [0.092, 0.20625, 0], [0.092, 0.06875, 0], [0.092, -0.06875, 0], [0.092, -0.20625, 0],
    [0.276, 0.20625, 0], [0.276, 0.06875, 0], [0.276, -0.06875, 0], [0.276, -0.20625, 0],
    [0.368, 0, 0],
    [-0.47, 0.20625, 0.1], [-0.47, 0.06875, 0.1], [-0.47, -0.06875, 0.1], [-0.47, -0.20625, 0.1],
    [-0.276, 0.20625, 0.1], [-0.276, 0.06875, 0.1], [-0.276, -0.06875, 0.1], [-0.276, -0.20625, 0.1],
    [-0.092, 0.20625, 0.1], [-0.092, 0.06875, 0.1], [-0.092, -0.06875, 0.1], [-0.092, -0.20625, 0.1],
    [0.092, 0.20625, 0.1], [0.092, 0.06875, 0.1], [0.092, -0.06875, 0.1], [0.092, -0.20625, 0.1],
    [0.276, 0.20625, 0.1], [0.276, 0.06875, 0.1], [0.276, -0.06875, 0.1], [0.276, -0.20625, 0.1],
    [0.368, 0, 0.1],
])

# 2. Extraction des points images (u, v) depuis votre fichier PNG
# Remplacez 'votre_image.png' par votre fichier réel
try:
    # 1. Extraction des centroïdes pour chaque image
    # Note : nb_points=21 car c'est ce que vous avez mis dans la définition
    pts_2d_0 = extraire_centroides('Pronto-imageur-3D/img/damier0.jpg', nb_points=21)
    pts_2d_100 = extraire_centroides('Pronto-imageur-3D/img/damier100.jpg', nb_points=21)
    
    # 2. Concaténation verticale des deux tableaux (pour obtenir un tableau de 42 points)
    mR_points_2d = np.vstack((pts_2d_0, pts_2d_100))
   
    # 3. Calcul final
    # Vérifiez que len(M_points_3d) == len(mR_points_2d) soit bien 42 ici
    MRN_finale = calculer_MRN(M_points_3d, mR_points_2d)
    MR, t3R, intrinsèques, angles = analyser_physique(MRN_finale)

    print("-" * 30)
    print("coefficient t3R :", t3R)
    print("MATRICE MR :\n", MR)
    print("-" * 30)
    print(f"Centre optique : u0={intrinsèques[0]:.2f}, v0={intrinsèques[1]:.2f}")
    print(f"Focales (px)  : alpha_u={intrinsèques[2]:.2f}, alpha_v={intrinsèques[3]:.2f}")
    print("-" * 30)
    print(f"ANGLES D'ORIENTATION (Degrés) :")
    print(f"Phi (Lacet)   : {angles[0]:.2f}°")
    print(f"Theta (Tangage): {angles[1]:.2f}°")
    print(f"Psi (Roulis)  : {angles[2]:.2f}°")
    

except Exception as e:
    print("Erreur lors de l'acquisition :", e)