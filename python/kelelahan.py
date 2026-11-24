"""Logika "smart" tanpa kamera: kalibrasi ambang EAR dan skor kelelahan. Bisa diuji dengan data sintetis."""
import statistics
from collections import deque

AMBANG_BAWAAN = 0.25


class Kalibrator:
    """Mempelajari EAR normal pengemudi selama `durasi_s`, lalu ambang = clamp(0.75 x median, 0.15, 0.30)."""

    def __init__(self, durasi_s=10.0, min_sampel=50, maks_percobaan=3):
        self.durasi_s = durasi_s
        self.min_sampel = min_sampel
        self.maks_percobaan = maks_percobaan
        self.ambang = AMBANG_BAWAAN
        self.baseline = None
        self.status = 0          # 0 sedang/belum, 1 selesai, 2 gagal
        self.berjalan = False
        self._sampel = []
        self._t_mulai = 0.0
        self._percobaan = 0

    def mulai(self, t):
        if self.berjalan:
            return False
        self.berjalan = True
        self.status = 0
        self._percobaan = 1
        self._ulang(t)
        return True

    def _ulang(self, t):
        self._sampel = []
        self._t_mulai = t

    def tambah(self, t, ear):
        if not self.berjalan:
            return
        if ear is not None:
            self._sampel.append(ear)
        if t - self._t_mulai < self.durasi_s:
            return
        if len(self._sampel) >= self.min_sampel:
            # Ambang lama tetap dipakai sampai titik ini, baru diganti setelah sukses
            self.baseline = statistics.median(self._sampel)
            self.ambang = min(max(0.75 * self.baseline, 0.15), 0.30)
            self.status = 1
            self.berjalan = False
        elif self._percobaan < self.maks_percobaan:
            self._percobaan += 1
            self._ulang(t)
        else:
            self.status = 2
            self.berjalan = False


SARAN = {
    'SEGAR': 'Kondisi baik, tetap fokus',
    'WASPADA': 'Mulai lelah, minum air dan buka jendela',
    'LELAH': 'Disarankan istirahat 15 menit',
    'BAHAYA': 'Segera menepi dan istirahat',
    '-': 'Menunggu kalibrasi',
}


def level_dari_skor(skor):
    if skor < 0:
        return '-'
    if skor < 30:
        return 'SEGAR'
    if skor < 55:
        return 'WASPADA'
    if skor < 80:
        return 'LELAH'
    return 'BAHAYA'


def saran(level):
    return SARAN[level]


def _buang_lama(dq, batas, waktu=lambda x: x):
    while dq and waktu(dq[0]) <= batas:
        dq.popleft()


class PenilaiKelelahan:
    """Skor 0-100 dari PERCLOS 60 s, episode tutup >= 1 s (5 menit), dan microsleep >= 2 s (10 menit).
    Frame tanpa wajah tidak dihitung dan mengakhiri episode. Episode dicatat dengan waktu mulainya."""

    def __init__(self):
        self._frame = deque()          # (t, tertutup) 60 s terakhir
        self._tutup_panjang = deque()  # waktu mulai episode >= 1 s
        self._microsleep = deque()     # waktu mulai episode >= 2 s
        self._mulai_tutup = None
        self._sudah_panjang = False
        self._sudah_micro = False

    def tambah(self, t, ear, ambang):
        if ear is None:
            self._mulai_tutup = None
            return
        tertutup = ear < ambang
        self._frame.append((t, tertutup))
        _buang_lama(self._frame, t - 60, lambda f: f[0])
        if not tertutup:
            self._mulai_tutup = None
            return
        if self._mulai_tutup is None:
            self._mulai_tutup = t
            self._sudah_panjang = self._sudah_micro = False
        durasi = t - self._mulai_tutup
        if durasi >= 1.0 and not self._sudah_panjang:
            self._sudah_panjang = True
            self._tutup_panjang.append(self._mulai_tutup)
        if durasi >= 2.0 and not self._sudah_micro:
            self._sudah_micro = True
            self._microsleep.append(self._mulai_tutup)

    def perclos60(self, t):
        _buang_lama(self._frame, t - 60, lambda f: f[0])
        if not self._frame:
            return 0.0
        return 100.0 * sum(1 for _, tutup in self._frame if tutup) / len(self._frame)

    def tutup_panjang_5m(self, t):
        _buang_lama(self._tutup_panjang, t - 300)
        return len(self._tutup_panjang)

    def microsleep_10m(self, t):
        _buang_lama(self._microsleep, t - 600)
        return len(self._microsleep)

    def skor(self, t, kalibrasi_siap):
        if not kalibrasi_siap:
            return -1
        nilai = (60 * min(self.perclos60(t) / 30.0, 1) + 25 * min(self.tutup_panjang_5m(t) / 3, 1)
                 + 15 * min(self.microsleep_10m(t) / 2, 1))
        return round(nilai)
