import numpy as np
from scipy import linalg

class CalibratorEngine:
    def __init__(self, sensitivity=256000.0):
        self.sensitivity = sensitivity
        self.b = np.zeros([3, 1])
        self.A_1 = np.eye(3)

    def ellipsoid_fit(self, s):
        # Design matrix D
        D = np.array([s[0]**2., s[1]**2., s[2]**2.,
                      2.*s[1]*s[2], 2.*s[0]*s[2], 2.*s[0]*s[1],
                      2.*s[0], 2.*s[1], 2.*s[2], np.ones_like(s[0])])

        S = np.dot(D, D.T)
        S_11 = S[:6,:6]
        S_12 = S[:6,6:]
        S_21 = S[6:,:6]
        S_22 = S[6:,6:]

        C = np.array([[-1, 1, 1, 0, 0, 0], [1, -1, 1, 0, 0, 0], [1, 1, -1, 0, 0, 0],
                      [0, 0, 0, -4, 0, 0], [0, 0, 0, 0, -4, 0], [0, 0, 0, 0, 0, -4]])

        E = np.dot(linalg.inv(C), S_11 - np.dot(S_12, np.dot(linalg.inv(S_22), S_21)))
        E_w, E_v = np.linalg.eig(E)
        v_1 = E_v[:, np.argmax(E_w)]
        if v_1[0] < 0: v_1 = -v_1
        v_2 = np.dot(np.dot(-np.linalg.inv(S_22), S_21), v_1)

        M = np.array([[v_1[0], v_1[5], v_1[4]], [v_1[5], v_1[1], v_1[3]], [v_1[4], v_1[3], v_1[2]]])
        n = np.array([[v_2[0]], [v_2[1]], [v_2[2]]])
        d = v_2[3]
        return M, n, d

    def calibrate_data(self, raw_lsb_data):
        # 1. Conversion LSB -> g
        data_g = raw_lsb_data / self.sensitivity
        
        # 2. Fit Ellipsoid
        M, n, d = self.ellipsoid_fit(data_g.T)
        
        # 3. Calcul paramètres de correction
        M_1 = linalg.inv(M)
        self.b = -np.dot(M_1, n)
        # On normalise pour que la sphère soit de rayon 1.0g
        val = np.dot(n.T, np.dot(M_1, n)) - d

        if val <= 0 or not np.isfinite(val):
            raise ValueError(f"Calibration instable, valeur sqrt invalide: {val}")

        scale = 1.0 / np.sqrt(val)
        self.A_1 = np.real(scale * linalg.sqrtm(M))
        print(val)
        # 4. Appliquer la correction : (Raw - Bias) * A_1
        calibrated_g = []
        for row in data_g:
            row_reshaped = row.reshape(3, 1)
            cal = np.dot(self.A_1, (row_reshaped - self.b))
            calibrated_g.append(cal.flatten())
            
        return data_g, np.array(calibrated_g)
