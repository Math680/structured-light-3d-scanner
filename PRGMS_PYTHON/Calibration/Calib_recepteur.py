import numpy as np

def calibrer_recepteur_dlt():
    # 1. Données Mi (Xi, Yi, Zi) - 18 points
    M = np.array([
        [-497.5, 234, 0], [-497.5, 0, 0], [-497.5, -234, 0],
        [0, 311, 0], [0, 0, 0], [0, -311, 0],
        [497.5, 234, 0], [497.5, 0, 0], [497.5, -234, 0],
        [-497.5, 234, 100], [-497.5, 0, 100], [-497.5, -234, 100],
        [0, 311, 100], [0, 0, 100], [0, -311, 100],
        [497.5, 234, 100], [497.5, 0, 100], [497.5, -234, 100]
    ])

    # 2. Données mRi (uRi, vRi) - 18 points
    mR = np.array([
        [165, 209], [539, 209], [913, 209],
        [120, 959], [539, 959], [967, 959],
        [257, 1517], [539, 1517], [822, 1517],
        [127, 195], [539, 195], [951, 195],
        [85, 1010], [539, 1010], [1005, 1010],
        [236, 1603], [539, 1603], [843, 1603]
    ])

    n = len(M)
    # 3. Construction de la matrice B (2n x 11) et du vecteur c (2n x 1)
    B = np.zeros((2 * n, 11))
    c = np.zeros((2 * n, 1))

    for i in range(n):
        Xi, Yi, Zi = M[i]
        ui, vi = mR[i]
        
        # Ligne pour uRi (Equation 30)
        B[2*i] = [Xi, Yi, Zi, 1, 0, 0, 0, 0, -ui*Xi, -ui*Yi, -ui*Zi]
        c[2*i] = ui
        
        # Ligne pour vRi (Equation 30)
        B[2*i+1] = [0, 0, 0, 0, Xi, Yi, Zi, 1, -vi*Xi, -vi*Yi, -vi*Zi]
        c[2*i+1] = vi

    # 4. Résolution par la pseudo-inverse (Equation 31)
    # xR = (Bt * B)^-1 * Bt * c
    Bt = B.T
    xR = np.linalg.inv(Bt @ B) @ Bt @ c

    # 5. Reconstruction de la matrice MRN (3x4)
    # Note: m34N est fixé à 1 par construction du système
    MRN_valeurs = np.append(xR, [1.0])
    MRN = MRN_valeurs.reshape((3, 4))

    print("Matrice de projection MRN calculée :")
    print(MRN)
    
    return MRN

if __name__ == "__main__":
    calibrer_recepteur_dlt()