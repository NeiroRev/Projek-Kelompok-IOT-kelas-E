import os
import unittest
from types import SimpleNamespace

import numpy as np

from deteksi_wajah import MATA_KANAN, MATA_KIRI, buat_landmarker, deteksi, hitung_ear

MODEL = os.path.join(os.path.dirname(__file__), 'models', 'face_landmarker.task')
W, H = 640, 480


def ear_sintetis(buka):
    """478 landmark tiruan; hanya 12 titik mata yang diisi (lebar mata 30 px, bukaan +-buka px)."""
    lm = [SimpleNamespace(x=0.0, y=0.0) for _ in range(478)]
    for idx, cx in ((MATA_KIRI, 250), (MATA_KANAN, 390)):
        cy, lebar = 200, 30
        titik = [(cx - lebar / 2, cy), (cx - lebar / 6, cy - buka), (cx + lebar / 6, cy - buka),
                 (cx + lebar / 2, cy), (cx + lebar / 6, cy + buka), (cx - lebar / 6, cy + buka)]
        for i, (x, y) in zip(idx, titik):
            lm[i] = SimpleNamespace(x=x / W, y=y / H)
    return (hitung_ear(MATA_KIRI, lm, W, H) + hitung_ear(MATA_KANAN, lm, W, H)) / 2


class TesDeteksiWajah(unittest.TestCase):
    def test_ear_mata_terbuka_dan_tertutup(self):
        self.assertAlmostEqual(ear_sintetis(buka=5.0), 0.333, places=3)
        self.assertAlmostEqual(ear_sintetis(buka=0.5), 0.033, places=3)

    def test_frame_kosong_tanpa_wajah(self):
        lm = buat_landmarker(MODEL)
        self.assertIsNone(deteksi(lm, np.zeros((H, W, 3), np.uint8), 0))


if __name__ == '__main__':
    unittest.main()
