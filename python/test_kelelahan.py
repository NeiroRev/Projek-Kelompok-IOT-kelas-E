import unittest

from kelelahan import Kalibrator

FPS = 30


def jalankan(k, t0, detik, ear_fn):
    """Kirim frame 30 fps selama `detik` mulai t0; ear_fn(i) memberi EAR frame ke-i (None = wajah hilang)."""
    n = round(detik * FPS)
    for i in range(n):
        k.tambah(t0 + i / FPS, ear_fn(i))
    return t0 + n / FPS


class TesKalibrator(unittest.TestCase):
    def test_ambang_dari_median(self):
        k = Kalibrator()
        k.mulai(0.0)
        # 320 frame: tiap frame ke-16 kedipan 0.05 (20 kedipan), sisanya 0.30
        jalankan(k, 0.0, 320 / FPS, lambda i: 0.05 if i % 16 == 0 else 0.30)
        self.assertEqual(k.status, 1)
        self.assertFalse(k.berjalan)
        self.assertAlmostEqual(k.baseline, 0.30)
        self.assertAlmostEqual(k.ambang, 0.225)

    def test_ambang_dijepit(self):
        atas = Kalibrator(); atas.mulai(0.0)
        jalankan(atas, 0.0, 10.5, lambda i: 0.45)
        self.assertAlmostEqual(atas.ambang, 0.30)
        bawah = Kalibrator(); bawah.mulai(0.0)
        jalankan(bawah, 0.0, 10.5, lambda i: 0.12)
        self.assertAlmostEqual(bawah.ambang, 0.15)

    def test_ambang_lama_dipakai_saat_kalibrasi_ulang(self):
        k = Kalibrator(); k.mulai(0.0)
        t = jalankan(k, 0.0, 10.5, lambda i: 0.30)
        self.assertAlmostEqual(k.ambang, 0.225)
        self.assertTrue(k.mulai(t))
        t = jalankan(k, t, 5.0, lambda i: 0.20)
        self.assertEqual(k.status, 0)
        self.assertAlmostEqual(k.ambang, 0.225)  # belum berubah di tengah kalibrasi
        jalankan(k, t, 6.0, lambda i: 0.20)
        self.assertAlmostEqual(k.ambang, 0.15)

    def test_gagal_tiga_kali(self):
        k = Kalibrator(); k.mulai(0.0)
        # wajah hanya terlihat 1 dari 10 frame -> +-30 sampel per 10 s
        jalankan(k, 0.0, 35.0, lambda i: 0.30 if i % 10 == 0 else None)
        self.assertEqual(k.status, 2)
        self.assertFalse(k.berjalan)
        self.assertAlmostEqual(k.ambang, 0.25)
        self.assertIsNone(k.baseline)

    def test_gagal_setelah_pernah_sukses_mempertahankan_ambang(self):
        k = Kalibrator(); k.mulai(0.0)
        t = jalankan(k, 0.0, 10.5, lambda i: 0.30)
        k.mulai(t)
        jalankan(k, t, 35.0, lambda i: None)
        self.assertEqual(k.status, 2)
        self.assertAlmostEqual(k.ambang, 0.225)
        self.assertAlmostEqual(k.baseline, 0.30)

    def test_mulai_saat_berjalan_ditolak(self):
        k = Kalibrator()
        self.assertTrue(k.mulai(0.0))
        t = jalankan(k, 0.0, 5.0, lambda i: 0.30)
        self.assertFalse(k.mulai(t))
        jalankan(k, t, 5.1, lambda i: 0.30)  # total 10.1 s sejak mulai pertama
        self.assertEqual(k.status, 1)

    def test_sampel_tanpa_wajah_diabaikan(self):
        k = Kalibrator(); k.mulai(0.0)
        # 10.5 s: 60 frame tanpa wajah bernilai None, sisanya 0.30 -> median tetap 0.30
        jalankan(k, 0.0, 10.5, lambda i: None if i < 60 else 0.30)
        self.assertEqual(k.status, 1)
        self.assertAlmostEqual(k.baseline, 0.30)

    def test_awal_memakai_ambang_bawaan(self):
        k = Kalibrator()
        self.assertAlmostEqual(k.ambang, 0.25)
        self.assertIsNone(k.baseline)
        self.assertEqual(k.status, 0)


if __name__ == '__main__':
    unittest.main()
