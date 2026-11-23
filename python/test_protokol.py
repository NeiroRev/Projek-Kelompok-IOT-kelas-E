import unittest

from protokol import PembacaSerial, PengirimKritis, baris_telemetri


class TesProtokol(unittest.TestCase):
    def test_format_baris(self):
        self.assertEqual(baris_telemetri(0.3124, 0.234, 0.312, 4.53, 12, 'SEGAR', 1),
                         b'T,0.312,0.234,0.312,4.5,12,SEGAR,1\n')

    def test_wajah_hilang(self):
        self.assertEqual(baris_telemetri(None, 0.25, None, 0.0, -1, '-', 0),
                         b'T,-1,0.250,-1,0.0,-1,-,0\n')

    def test_baca_perintah_terpotong(self):
        b = PembacaSerial()
        self.assertEqual(b.masukkan(b'CMD,KAL'), [])
        self.assertEqual(b.masukkan(b'IBRASI\n'), ['KALIBRASI'])

    def test_abaikan_debug(self):
        b = PembacaSerial()
        self.assertEqual(b.masukkan(b'Gagal memuat OLED\r\nCMD,KALIBRASI\r\n'), ['KALIBRASI'])

    def test_byte_rusak_tidak_crash(self):
        b = PembacaSerial()
        self.assertEqual(b.masukkan(b'\xff\xfe\nCMD,KALIBRASI\n'), ['KALIBRASI'])

    def test_buffer_tanpa_baris_baru_dibatasi(self):
        b = PembacaSerial()
        b.masukkan(b'x' * 5000)
        self.assertEqual(b.masukkan(b'\nCMD,KALIBRASI\n'), ['KALIBRASI'])
        self.assertLessEqual(len(b._sisa), 256)



class TesPengirimKritis(unittest.TestCase):
    def test_kirim_saat_berubah(self):
        k = PengirimKritis()
        self.assertTrue(k.perlu_kirim('0', 0.00))
        self.assertFalse(k.perlu_kirim('0', 0.03))  # status sama, belum 0,5 s
        self.assertTrue(k.perlu_kirim('W', 0.06))   # berubah -> langsung
        self.assertTrue(k.perlu_kirim('1', 0.09))

    def test_ulang_berkala_saat_status_sama(self):
        # Status '1' tetap dikirim ulang tiap 0,5 s: setelah tombol reset ditekan
        # sementara mata masih tertutup, alarm menyala lagi (perilaku awal sistem)
        k = PengirimKritis()
        self.assertTrue(k.perlu_kirim('1', 10.0))
        self.assertFalse(k.perlu_kirim('1', 10.49))
        self.assertTrue(k.perlu_kirim('1', 10.5))
        self.assertFalse(k.perlu_kirim('1', 10.6))


if __name__ == '__main__':
    unittest.main()
