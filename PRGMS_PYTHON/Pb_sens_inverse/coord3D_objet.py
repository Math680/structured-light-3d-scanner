import numpy as np
import os
import time

class Coord3D:
    def __init__(self, ME, MR):
        self.ME = ME
        self.MR = MR

    import numpy as np

    def reconstruct(self, uR_file, vR_file, uE_file, vE_file):
        # Chargement
        uR_grid = np.loadtxt(uR_file)
        vR_grid = np.loadtxt(vR_file)
        uE_grid = np.loadtxt(uE_file)
        vE_grid = np.loadtxt(vE_file)

        HR, WR = uR_grid.shape
        HE, WE = uE_grid.shape

        # Coordonnées caméra (vérité géométrique)
        vR, uR = np.meshgrid(
            np.arange(HR),
            np.arange(WR),
            indexing="ij"
        )

        # Cas simple : uE/vE déjà exprimés en pixels caméra
        if uE_grid.shape == (HR, WR):
            uE = uE_grid
            vE = vE_grid
        else:
            # Cas général : interpolation vers la grille caméra
            from scipy.interpolate import RegularGridInterpolator

            interp_uE = RegularGridInterpolator(
                (np.arange(HE), np.arange(WE)),
                uE_grid,
                bounds_error=False,
                fill_value=np.nan
            )

            interp_vE = RegularGridInterpolator(
                (np.arange(HE), np.arange(WE)),
                vE_grid,
                bounds_error=False,
                fill_value=np.nan
            )

            pts = np.column_stack((vR.ravel(), uR.ravel()))

            uE = interp_uE(pts).reshape(HR, WR)
            vE = interp_vE(pts).reshape(HR, WR)

        # Vectorisation
        uR = uR.ravel()
        vR = vR.ravel()
        uE = uE.ravel()
        vE = vE.ravel()

        # Masque de validité
        valid = np.isfinite(uE) & np.isfinite(vE)

        return uR[valid], vR[valid], uE[valid], vE[valid]


    def reconstruct_point(self, uE, vE, uR, vR):
        n = uE.size
        XYZ = np.zeros((n, 3))

        m1E, m2E, m3E = self.ME[0], self.ME[1], self.ME[2]
        m1R, m2R, m3R = self.MR[0], self.MR[1], self.MR[2]

        for i in range(n):
            A = np.array([
                uE[i] * m3E[:3] - m1E[:3],
                vE[i] * m3E[:3] - m2E[:3],
                uR[i] * m3R[:3] - m1R[:3],
                vR[i] * m3R[:3] - m2R[:3],
            ])

            b = np.array([
                m1E[3] - uE[i] * m3E[3],
                m2E[3] - vE[i] * m3E[3],
                m1R[3] - uR[i] * m3R[3],
                m2R[3] - vR[i] * m3R[3],
            ])

            XYZ[i], *_ = np.linalg.lstsq(A, b, rcond=None)

        return XYZ


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath("Pronto-Imageur-3D"))  # folder where script resides
    file_path = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "ME.txt")

    ME = np.loadtxt(file_path)
    file_path = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "MR.txt")


    MR = np.loadtxt(file_path)
    uE_file = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "uE.txt")
    uR_file = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "uRZoom.txt")
    vE_file = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "vE.txt")
    vR_file = os.path.join(script_dir, "Pronto-Imageur-3D/stockage", "vRZoom.txt")

    coord = Coord3D(ME,MR)

    uR, vR, uE, vE = coord.reconstruct(uR_file, vR_file, uE_file, vE_file)

    XYZ = coord.reconstruct_point(uE, vE, uR, vR)

    import matplotlib.pyplot as plt

    # --- XYZ : nuage 3D (N, 3) ---
    # uR, vR : coordonnées image caméra associées (N,)

    # Filtrage des points invalides
    valid = (
        np.isfinite(XYZ).all(axis=1) &
        (XYZ[:, 2] > 0) &        # devant la caméra
        (XYZ[:, 2] < 2000)       # profondeur max (à adapter)
    )

    XYZf = XYZ[valid]
    uRf = uR[valid]
    vRf = vR[valid]

    print("Points valides :", XYZf.shape[0])

    # Affichage 3D
    fig = plt.figure(figsize=(12, 5))

    ax = fig.add_subplot(121, projection="3d")
    ax.scatter(
        XYZf[:, 0],
        XYZf[:, 1],
        XYZf[:, 2],
        s=1
    )
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.set_title("Nuage de points 3D")

    # Carte de profondeur (projection XY colorée par Z)
    ax2 = fig.add_subplot(122)
    sc = ax2.scatter(
        XYZf[:, 0],
        XYZf[:, 1],
        c=XYZf[:, 2],
        s=1
    )
    plt.colorbar(sc, ax=ax2, label="Z (profondeur)")
    ax2.set_aspect("equal")
    ax2.set_title("Carte de profondeur")

    plt.tight_layout()
    plt.show()
