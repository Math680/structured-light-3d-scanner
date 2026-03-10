import numpy as np
import cv2

def calibrate_camera_custom(pts_2d, pts_3d):
    """
    Calcule la matrice de projection M via la méthode DLT (Eq. 30 & 31)
    """
    num_points = pts_2d.shape[0]
    B = []

    for i in range(num_points):
        X, Y, Z = pts_3d[i]
        u, v = pts_2d[i]
        
        # Construction des deux lignes de la matrice B pour chaque point (Eq. 30)
        # Ligne pour u
        B.append([X, Y, Z, 1, 0, 0, 0, 0, -u*X, -u*Y, -u*Z])
        # Ligne pour v
        B.append([0, 0, 0, 0, X, Y, Z, 1, -v*X, -v*Y, -v*Z])

    B = np.array(B)
    c = pts_2d.reshape(-1, 1) # Le vecteur des u1, v1, u2, v2...

    # Résolution au sens des moindres carrés (Eq. 31)
    # x = (B^T * B)^-1 * B^T * c
    m_vector, residuals, rank, s = np.linalg.lstsq(B, c, rcond=None)
    
    # On ajoute le dernier coefficient m34 qui est normalisé à 1 (selon l'image)
    m_vector = np.append(m_vector, [1.0])
    
    # Mise en forme de la matrice perspective 3x4
    M_NR = m_vector.reshape((3, 4))
    
    return M_NR

def extract_red_points(image_path):
    """
    Extrait les coordonnées des points rouges sur l'image
    """
    img = cv2.imread(image_path)
    # Conversion en HSV pour mieux isoler le rouge
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Masque pour le rouge (deux plages nécessaires car le rouge est aux extrémités du spectre)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    
    mask = cv2.bitwise_or(cv2.inRange(hsv, lower_red1, upper_red1),
                          cv2.inRange(hsv, lower_red2, upper_red2))
    
    # Trouver les centres des points (centroids)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    points = []
    for cnt in contours:
        M = cv2.moments(cnt)
        if M["m00"] != 0:
            cX = int(M["m10"] / M["m00"])
            cY = int(M["m01"] / M["m00"])
            points.append([cX, cY])
    
   
    # Ici on trie par Y puis par X (balayage haut-bas, gauche-droite)
    points = sorted(points, key=lambda p: (p[1], p[0]))
    return np.array(points)

# --- CONFIGURATION DES DONNÉES DE TEST ---

# 1. Simulation de points 3D (9 points à Z=0 et 9 points à Z=100)
# Imaginons un carré de 3x3 points espacés de 50mm
grid_3d = np.array([[x, y, 0] for y in [0, 50, 100] for x in [0, 50, 100]])
pts_3d_z0 = grid_3d
pts_3d_z100 = grid_3d.copy()
pts_3d_z100[:, 2] = 100 
pts_3d = np.vstack((pts_3d_z0, pts_3d_z100)) # Total 18 points

# 2. Simulation de points 2D (À remplacer par l'extraction réelle)
# Ici, je crée des points fictifs pour que le code tourne
pts_2d = np.random.uniform(100, 500, (18, 2)) 

# --- EXÉCUTION ---

# Dans votre cas réel : 
# pts_2d = extract_red_points("votre_image.png")

M_final = calibrate_camera_custom(pts_2d, pts_3d)

print("Matrice Perspective M_NR calculée :")
print(M_final)

# --- EXTRACTION DES PARAMÈTRES EXTRINSÈQUES ---
# M = K [R | t]
# On peut décomposer M en utilisant la décomposition QR sur les 3 premières colonnes
A = M_final[:, :3]
b = M_final[:, 3]

# Décomposition QR pour obtenir la rotation et l'intrinsèque (simplifié)
# Note : C'est une approximation si K est inconnu
R, K_estime = np.linalg.qr(np.linalg.inv(A))
R = np.linalg.inv(R)
t = np.linalg.inv(K_estime) @ b

print("\nRotation (R) estimée :")
print(R)
print("\nVecteur de translation (t) estimé :")
print(t)