import numpy as np

class Coord3D:
    def __init__(self, ME, MR):
        self.ME = ME
        self.MR = MR

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
    uE = np.loadtxt("stockage/uE.txt")
    uR = np.loadtxt("stockage/uRZoom.txt")
    vE = np.loadtxt("stockage/vE.txt")
    vR = np.loadtxt("stockage/vRZoom.txt")

    coord = Coord3D(ME,MR)

    coord.reconstruct_point(uE, vE, uR, vR)