import numpy as np

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
        A = []
        b = []

        for M, u, v in [(self.ME, uE, vE), (self.MR, uR, vR)]:
            m1, m2, m3 = M[0], M[1], M[2]
            A.append(u * m3[:3] - m1[:3])
            A.append(v * m3[:3] - m2[:3])
            b.append(m1[3] - u * m3[3])
            b.append(m2[3] - v * m3[3])

        A = np.array(A)
        b = np.array(b)

        X, *_ = np.linalg.lstsq(A, b, rcond=None)
        return X  # (X, Y, Z)

if __name__ == "__main__":
    ME = np.loadtxt("stockage/ME.txt")
    MR = np.loadtxt("stockage/MR.txt")
    uE_file = np.loadtxt("stockage/uE.txt")
    uR_file = np.loadtxt("stockage/uRZoom.txt")
    vE_file = np.loadtxt("stockage/vE.txt")
    vR_file = np.loadtxt("stockage/vRZoom.txt")

    coord = Coord3D(ME,MR)

    uR, vR, uE, vE = coord.reconstruct(uR_file, vR_file, uE_file, vE_file)

    coord.reconstruct_point(uE, vE, uR, vR)