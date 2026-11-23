"""Protokol serial v2 laptop <-> ESP32 (lihat docs/superpowers/specs/2026-11-19-dashboard-smart-design.md 5.4).
Karakter tunggal '0'/'W'/'1' tetap dikirim langsung di main.py; modul ini hanya baris telemetri dan perintah."""

MAKS_BARIS = 256
ULANG_KRITIS_S = 0.5


def baris_telemetri(ear, ambang, baseline, perclos, skor, level, kal):
    ear_s = '-1' if ear is None else f'{ear:.3f}'
    base_s = '-1' if baseline is None else f'{baseline:.3f}'
    return f'T,{ear_s},{ambang:.3f},{base_s},{perclos:.1f},{skor},{level},{kal}\n'.encode('ascii')


class PembacaSerial:
    """Mengumpulkan byte dari ESP32 dan mengembalikan perintah 'CMD,<nama>' yang sudah lengkap.
    Baris lain (pesan debug firmware) diabaikan."""

    def __init__(self):
        self._sisa = b''

    def masukkan(self, data):
        self._sisa += data
        *baris, self._sisa = self._sisa.split(b'\n')
        self._sisa = self._sisa[-MAKS_BARIS:]  # baris tanpa '\n' yang terlalu panjang adalah sampah
        perintah = []
        for b in baris:
            teks = b.decode('ascii', 'ignore').strip()
            if teks.startswith('CMD,'):
                perintah.append(teks[4:])
        return perintah


class PengirimKritis:
    """Kirim karakter kritis hanya saat status berubah (dari versi Brian), tetapi tetap ulangi tiap 0,5 s
    agar ESP32 yang baru restart atau baru di-reset tetap menerima status terkini."""

    def __init__(self):
        self._terakhir = None
        self._t_kirim = 0.0

    def perlu_kirim(self, karakter, t):
        if karakter != self._terakhir or t - self._t_kirim >= ULANG_KRITIS_S:
            self._terakhir = karakter
            self._t_kirim = t
            return True
        return False
