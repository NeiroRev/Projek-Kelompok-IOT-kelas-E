import unittest

from protokol import PembacaSerial, baris_telemetri


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


if __name__ == '__main__':
    unittest.main()
