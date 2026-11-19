import unittest

from kelelahan import Kalibrator, PenilaiKelelahan, level_dari_skor, saran

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


def isi(p, t0, pola, ambang=0.25):
    """pola: daftar (detik, ear); kirim ke penilai pada 30 fps. Kembalikan waktu akhir."""
    t = t0
    for detik, ear in pola:
        for _ in range(round(detik * FPS)):
            p.tambah(t, ear, ambang)
            t += 1 / FPS
    return t


class TesPenilaiKelelahan(unittest.TestCase):
    def test_kedipan_tidak_menaikkan_skor(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(3.8, 0.30), (0.2, 0.05)] * 15)  # 60 s, kedip 0.2 s tiap 4 s
        self.assertEqual(p.tutup_panjang_5m(t), 0)
        self.assertEqual(p.microsleep_10m(t), 0)
        self.assertAlmostEqual(p.perclos60(t), 5.0, delta=0.5)
        self.assertLess(p.skor(t, True), 30)

    def test_perclos_dan_episode(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(18.5, 0.30), (1.5, 0.05)] * 3)  # 60 s, 3 episode tutup 1.5 s
        self.assertEqual(p.tutup_panjang_5m(t), 3)
        self.assertEqual(p.microsleep_10m(t), 0)
        self.assertAlmostEqual(p.perclos60(t), 7.5, delta=0.5)

    def test_microsleep_dihitung_sekali(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(5.0, 0.30), (5.0, 0.05), (5.0, 0.30)])
        self.assertEqual(p.microsleep_10m(t), 1)
        self.assertEqual(p.tutup_panjang_5m(t), 1)

    def test_skor_dan_level(self):
        p = PenilaiKelelahan()
        # 60 s: tutup 9 s, 9 s, 1.5 s -> perclos 32.5 %, 3 tutup panjang, 2 microsleep
        t = isi(p, 0.0, [(10.0, 0.30), (9.0, 0.05), (10.0, 0.30), (9.0, 0.05), (10.0, 0.30), (1.5, 0.05), (10.5, 0.30)])
        self.assertEqual(p.tutup_panjang_5m(t), 3)
        self.assertEqual(p.microsleep_10m(t), 2)
        self.assertEqual(p.skor(t, True), 100)
        self.assertEqual(level_dari_skor(p.skor(t, True)), 'BAHAYA')
        self.assertEqual([level_dari_skor(s) for s in (0, 29, 30, 54, 55, 79, 80, 100)],
                         ['SEGAR', 'SEGAR', 'WASPADA', 'WASPADA', 'LELAH', 'LELAH', 'BAHAYA', 'BAHAYA'])

    def test_jendela_kedaluwarsa(self):
        p = PenilaiKelelahan()
        isi(p, 0.0, [(3.0, 0.05), (0.1, 0.30)])  # satu episode 3 s dimulai t=0
        self.assertEqual(p.microsleep_10m(300.0), 1)
        self.assertEqual(p.tutup_panjang_5m(301.0), 0)
        self.assertEqual(p.microsleep_10m(599.0), 1)
        self.assertEqual(p.microsleep_10m(601.0), 0)
        self.assertEqual(p.perclos60(70.0), 0.0)

    def test_wajah_hilang_tidak_dihitung(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(60.0, None)])
        self.assertEqual(p.perclos60(t), 0.0)
        self.assertEqual(p.tutup_panjang_5m(t), 0)
        self.assertEqual(p.skor(t, True), 0)

    def test_wajah_hilang_mengakhiri_episode(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(0.9, 0.05), (2.0, None), (0.9, 0.05), (1.0, 0.30)])
        self.assertEqual(p.tutup_panjang_5m(t), 0)  # dua potongan 0.9 s, bukan satu episode 3.8 s

    def test_skor_sebelum_kalibrasi(self):
        p = PenilaiKelelahan()
        t = isi(p, 0.0, [(10.0, 0.05)])
        self.assertEqual(p.skor(t, False), -1)
        self.assertEqual(level_dari_skor(-1), '-')

    def test_saran(self):
        self.assertEqual(saran('SEGAR'), 'Kondisi baik, tetap fokus')
        self.assertEqual(saran('WASPADA'), 'Mulai lelah, minum air dan buka jendela')
        self.assertEqual(saran('LELAH'), 'Disarankan istirahat 15 menit')
        self.assertEqual(saran('BAHAYA'), 'Segera menepi dan istirahat')
        self.assertEqual(saran('-'), 'Menunggu kalibrasi')


if __name__ == '__main__':
    unittest.main()
