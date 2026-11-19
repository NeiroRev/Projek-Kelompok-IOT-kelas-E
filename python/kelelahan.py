"""Logika "smart" tanpa kamera: kalibrasi ambang EAR dan skor kelelahan. Bisa diuji dengan data sintetis."""
import statistics

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
