"""Protokol serial v2 laptop <-> ESP32 (lihat docs/superpowers/specs/2026-11-19-dashboard-smart-design.md 5.4).
Karakter tunggal '0'/'W'/'1' tetap dikirim langsung di main.py; modul ini hanya baris telemetri dan perintah."""

MAKS_BARIS = 256


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
