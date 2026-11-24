# Dashboard Monitoring + Fitur Smart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menambah kalibrasi otomatis, skor kelelahan prediktif, eskalasi wajib istirahat, telemetri MQTT dua arah dari ESP32, dan dashboard Node-RED + MongoDB untuk demo final project.

**Architecture:** `main.py` (laptop) mendeteksi wajah dengan MediaPipe Tasks FaceLandmarker, menghitung fitur smart di modul murni `kelelahan.py`, mengirim `'0'/'W'/'1'` (kritis) dan baris `T,...` 1 Hz lewat serial. ESP32 menjalankan aktuator, eskalasi, dan menjadi gerbang MQTT (telemetri 1 Hz dengan timer sendiri, log, status LWT, perintah). Node-RED subscribe, menyimpan ke MongoDB, dan menampilkan dashboard.

**Tech Stack:** Python 3.14 + opencv-python + mediapipe (Tasks API) + pyserial · ESP32 Arduino (Adafruit_SSD1306, PubSubClient) · MQTT broker.hivemq.com · Node-RED + node-red-dashboard 3.6.6 + node-red-node-mongodb 0.2.5 · MongoDB 9.0.4.

**Spec:** `docs/superpowers/specs/2026-11-19-dashboard-smart-design.md`

## Global Constraints

- Jalur kritis tidak berubah: karakter tunggal `'0'`, `'W'`, `'1'` diproses segera; urutan di alarm tetap aktuator → OLED → MQTT; alarm tidak bergantung pada WiFi/broker/Node-RED.
- Tidak ada perintah dashboard yang mematikan alarm; alarm hanya mati lewat tombol fisik GPIO 4.
- Pin tetap sesuai `esp32/sketch.ino` (PR #1). Serial 115200 bps.
- Tidak ada data dummy di dashboard saat demo.
- Python: dependensi hanya `opencv-python`, `mediapipe`, `pyserial`; uji memakai `unittest` bawaan (`python -m unittest`).
- Kalibrasi: 10 detik, `baseline = median`, `ambang = clamp(0.75*baseline, 0.15, 0.30)`, bawaan 0.25, minimal 50 sampel, maksimal 3 percobaan, `kal` 0/1/2.
- Skor: `round(60*min(perclos60/0.30,1) + 25*min(tutup_panjang_5m/3,1) + 15*min(microsleep_10m/2,1))`; `-1` sebelum kalibrasi pertama selesai. Level 0–29 SEGAR, 30–54 WASPADA, 55–79 LELAH, 80–100 BAHAYA.
- Saran: SEGAR "Kondisi baik, tetap fokus" · WASPADA "Mulai lelah, minum air dan buka jendela" · LELAH "Disarankan istirahat 15 menit" · BAHAYA "Segera menepi dan istirahat".
- Baris serial: `T,<ear>,<ambang>,<baseline>,<perclos>,<skor>,<level>,<kal>\n` (ear 3 desimal, -1 bila wajah hilang; perclos 1 desimal) dan `CMD,KALIBRASI\n`.
- MQTT prefix `kelompok8/deteksi_kantuk/`: `telemetri` (QoS0, 1 Hz timer ESP32, flag `kamera` true bila `T` ≤ 3 s), `log`, `status` (retain, LWT `offline`), `perintah` (`KALIBRASI`, `TES_ALARM`).
- Eskalasi: ≥ 2 alarm dalam 10 menit → `wajib_istirahat`; hilang setelah 10 menit tanpa alarm. `KALIBRASI` ditolak saat alarm atau wajib istirahat.
- MongoDB `localhost:27017`, database `deteksi_kantuk`, collection `telemetri` dan `kejadian`, simpan `msg.payload` + `diterima`.

## Review Focus

- Kamera/laptop mati sementara ESP32 online → telemetri tetap 1 Hz dengan `kamera:false` dan field laptop `null`; dashboard menulis "kamera/laptop TERPUTUS", bukan OFFLINE. (Task 5)
- Baris serial rusak/terpotong (> 95 karakter tanpa `\n`, jumlah field salah) → ESP32 membuang baris, tidak crash, dan `'1'` berikutnya tetap memicu alarm. (Task 5)
- Wajah hilang lama → frame tanpa wajah tidak dihitung ke PERCLOS dan tidak memulai episode; skor tidak melonjak. (Task 3)
- `KALIBRASI` ditekan berulang/saat kalibrasi berjalan → tidak memulai ulang berkali-kali; saat alarm → ditolak dengan event log. (Task 4, Task 6)
- Broker tidak terjangkau saat level naik ke LELAH → chirp dan OLED tetap jalan; publish gagal diam-diam. (Task 6)

---

### Task 1: Pindah ke MediaPipe Tasks FaceLandmarker + kunci dependensi

**Files:**
- Create: `python/models/face_landmarker.task` (unduh dari `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`)
- Create: `python/deteksi_wajah.py`
- Create: `python/test_deteksi_wajah.py`
- Modify: `python/main.py` (inisialisasi Face Mesh, `hitung_ear`, loop)
- Modify: `python/requirements.txt`

**Interfaces:**
- Produces: `buat_landmarker(path_model: str) -> FaceLandmarker` (mode `VIDEO`, `num_faces=1`); `deteksi(landmarker, frame_bgr, t_ms: int) -> list | None` (daftar 478 landmark ternormalisasi wajah pertama, atau `None`); `hitung_ear(titik_mata: list[int], landmarks: list, w: int, h: int) -> float` (pindah ke `deteksi_wajah.py`, akses `landmarks[p].x/.y`); konstanta `MATA_KIRI`, `MATA_KANAN` (nilai sama dengan `main.py` sekarang).

- [ ] **Step 1:** Pasang dependensi: `python -m pip install opencv-python mediapipe pyserial`, lalu catat versi dengan `python -m pip freeze`.
- [ ] **Step 2:** Unduh model ke `python/models/face_landmarker.task`; pastikan ukuran ± 3,6 MB.
- [ ] **Step 3: Tulis tes yang gagal** `python/test_deteksi_wajah.py`:

```python
class TesDeteksiWajah(unittest.TestCase):
    # ear_sintetis(buka) membangun 478 landmark tiruan (hanya 12 titik mata yang diisi) lalu memanggil hitung_ear
    def test_ear_mata_terbuka_dan_tertutup(self):
        # titik sintetis seperti uji makalah: lebar 30 px, bukaan ±5 px -> 0.333; ±0.5 px -> 0.033
        self.assertAlmostEqual(ear_sintetis(buka=5.0), 0.333, places=3)
        self.assertAlmostEqual(ear_sintetis(buka=0.5), 0.033, places=3)
    def test_frame_kosong_tanpa_wajah(self):
        lm = buat_landmarker(MODEL)
        self.assertIsNone(deteksi(lm, np.zeros((480, 640, 3), np.uint8), 0))
```

- [ ] **Step 4:** Jalankan `cd python && python -m unittest test_deteksi_wajah -v` → FAIL (modul belum ada).
- [ ] **Step 5:** Implementasi `deteksi_wajah.py`; `main.py` memakai `deteksi()` dengan `t_ms` monoton (`int(time.monotonic()*1000)`), menggantikan `mp.solutions.face_mesh`.
- [ ] **Step 6:** Jalankan ulang tes → PASS. Smoke test manual: `python main.py` dengan webcam menampilkan "STATUS: FOKUS" dan nilai EAR berubah saat mata ditutup.
- [ ] **Step 7:** Kunci `requirements.txt` ke versi dari Step 1 (`opencv-python==…`, `mediapipe==…`, `pyserial==…`).
- [ ] **Step 8: Commit** `feat(python): pindah ke MediaPipe Tasks FaceLandmarker`.

### Task 2: Kalibrator otomatis

**Files:**
- Create: `python/kelelahan.py`
- Create: `python/test_kelelahan.py`

**Interfaces:**
- Produces: `class Kalibrator` dengan `__init__(durasi_s=10.0, min_sampel=50, maks_percobaan=3)`, `mulai(t: float) -> bool` (False bila sedang berjalan), `tambah(t: float, ear: float | None) -> None`, properti `ambang: float` (awal 0.25), `baseline: float | None`, `status: int` (0 sedang, 1 selesai, 2 gagal), `berjalan: bool`.

- [ ] **Step 1: Tes yang gagal:**

```python
def test_ambang_dari_median(self):          # 300 sampel 0.30 + 20 kedipan 0.05 -> baseline 0.30, ambang 0.225, status 1
def test_ambang_dijepit(self):              # baseline 0.45 -> ambang 0.30 ; baseline 0.12 -> ambang 0.15
def test_ambang_lama_dipakai_saat_kalibrasi_ulang(self):  # setelah sukses 0.225, mulai() lagi -> ambang tetap 0.225 sampai selesai
def test_gagal_tiga_kali(self):             # tiap percobaan hanya 30 sampel -> setelah 3x status 2, ambang tetap nilai terakhir (0.25 bila belum pernah sukses)
def test_mulai_saat_berjalan_ditolak(self): # mulai() kedua sebelum 10 s -> False, durasi tidak diulang
def test_sampel_tanpa_wajah_diabaikan(self):# tambah(t, None) tidak menambah sampel
```

- [ ] **Step 2:** `python -m unittest test_kelelahan -v` → FAIL.
- [ ] **Step 3:** Implementasi `Kalibrator` (pakai `statistics.median`). Percobaan gagal otomatis diulang dengan `mulai` internal sampai 3 kali.
- [ ] **Step 4:** Tes → PASS.
- [ ] **Step 5: Commit** `feat(python): kalibrasi EAR otomatis per pengemudi`.

### Task 3: Penilai skor kelelahan

**Files:**
- Modify: `python/kelelahan.py`
- Modify: `python/test_kelelahan.py`

**Interfaces:**
- Produces: `class PenilaiKelelahan` dengan `tambah(t: float, ear: float | None, ambang: float) -> None` (per frame), `perclos60(t) -> float` (persen 0–100), `tutup_panjang_5m(t) -> int`, `microsleep_10m(t) -> int`, `skor(t, kalibrasi_siap: bool) -> int`; fungsi `level_dari_skor(skor: int) -> str` (`"-"` untuk -1) dan `saran(level: str) -> str` (teks Global Constraints).

- [ ] **Step 1: Tes yang gagal** (30 fps sintetis):

```python
def test_kedipan_tidak_menaikkan_skor(self):   # 60 s mata terbuka + kedip 0.2 s tiap 4 s -> tutup_panjang 0, microsleep 0, skor < 30
def test_perclos_dan_episode(self):           # 60 s, 3 episode tutup 1.5 s -> tutup_panjang_5m == 3, microsleep_10m == 0
def test_microsleep_dihitung_sekali(self):    # satu episode 5 s -> microsleep_10m == 1
def test_skor_dan_level(self):                # perclos 30%, 3 tutup panjang, 2 microsleep -> skor 100, level BAHAYA; level_dari_skor(29)=="SEGAR", 30 WASPADA, 55 LELAH, 80 BAHAYA
def test_jendela_kedaluwarsa(self):           # episode pada t=0, cek t=601 -> microsleep_10m == 0; t=301 -> tutup_panjang_5m == 0
def test_wajah_hilang_tidak_dihitung(self):   # 60 s ear=None -> perclos60 == 0, tidak ada episode
def test_skor_sebelum_kalibrasi(self):        # skor(t, kalibrasi_siap=False) == -1
```

- [ ] **Step 2:** Tes → FAIL.
- [ ] **Step 3:** Implementasi dengan `collections.deque` berisi `(t, tertutup)` untuk 60 s, dan deque waktu episode untuk 5/10 menit. Episode dimulai saat EAR < ambang; dihitung "tutup panjang" saat durasinya mencapai 1 s dan "microsleep" saat mencapai 2 s (masing-masing sekali per episode). Frame `ear=None` tidak masuk jendela dan mengakhiri episode.
- [ ] **Step 4:** Tes → PASS.
- [ ] **Step 5: Commit** `feat(python): skor kelelahan prediktif dan level`.

### Task 4: Protokol serial dan integrasi `main.py`

**Files:**
- Create: `python/protokol.py`, `python/test_protokol.py`
- Modify: `python/main.py`

**Interfaces:**
- Consumes: Task 1–3.
- Produces: `baris_telemetri(ear: float | None, ambang: float, baseline: float | None, perclos: float, skor: int, level: str, kal: int) -> bytes` (format Global Constraints; `baseline` None → `-1`); `class PembacaSerial` dengan `masukkan(data: bytes) -> list[str]` mengembalikan perintah lengkap (`"KALIBRASI"`) dan mengabaikan baris lain/terpotong.

- [ ] **Step 1: Tes yang gagal:**

```python
def test_format_baris(self):  # baris_telemetri(0.3124,0.234,0.312,4.53,12,"SEGAR",1) == b"T,0.312,0.234,0.312,4.5,12,SEGAR,1\n"
def test_wajah_hilang(self):  # ear None -> b"T,-1,0.250,-1,0.0,-1,-,0\n"
def test_baca_perintah_terpotong(self):  # masukkan(b"CMD,KAL") == [] ; masukkan(b"IBRASI\n") == ["KALIBRASI"]
def test_abaikan_debug(self):  # masukkan(b"Gagal memuat OLED\nCMD,KALIBRASI\n") == ["KALIBRASI"]
```

- [ ] **Step 2:** Tes → FAIL, implementasi `protokol.py`, tes → PASS.
- [ ] **Step 3:** Integrasi `main.py`: kalibrasi otomatis saat start; tombol `c` dan `CMD,KALIBRASI` memanggil `Kalibrator.mulai` (abaikan bila `False`); pakai `kalibrator.ambang` menggantikan `BATAS_EAR`; kirim baris `T` tiap 1 s setelah karakter kritis frame itu; baca serial non-blocking (`esp.in_waiting`); tampilkan skor, level, saran, dan status kalibrasi di jendela video.
- [ ] **Step 4:** Verifikasi tanpa ESP32: `python main.py` (mode uji) menampilkan "KALIBRASI…" 10 s lalu ambang pribadi; mata ditutup 1,5 s berulang menaikkan level di layar.
- [ ] **Step 5: Commit** `feat(python): telemetri serial 1 Hz dan perintah kalibrasi`.

### Task 5: Firmware — parser serial, telemetri, status

**Files:**
- Modify: `esp32/sketch.ino`

**Interfaces:**
- Consumes: baris `T` (Task 4).
- Produces: topik `telemetri`/`status` (Global Constraints); fungsi `prosesBaris(const char*)`, `kirimTelemetri()`; variabel `levelTerakhir` (String level dari `T`) untuk Task 6.

- [ ] **Step 1:** Konstanta `WIFI_SSID`/`WIFI_PASS` di atas sketch (bawaan `Wokwi-GUEST`). Loop serial: karakter `'0'/'W'/'1'` di luar mode baris diproses seperti sekarang; `'T'` memulai mode baris sampai `\n`; buffer 96, kelebihan → buang baris. `prosesBaris` mem-parse 7 field; jumlah field salah → abaikan.
- [ ] **Step 2:** Timer 1 Hz `kirimTelemetri()` dengan JSON field spec; `kamera` true bila `T` terakhir ≤ 3000 ms; bila false field laptop `null`; `rssi = WiFi.RSSI()`.
- [ ] **Step 3:** `client.connect(id, willTopic=".../status", 1, true, "offline")` lalu publish `online` retain.
- [ ] **Step 4: Verifikasi** sintaks dengan `xtensa-esp32-elf-g++ -fsyntax-only` memakai header tiruan seperti di PR #1, lalu di Wokwi Serial Monitor ketik:
  `T,0.312,0.234,0.312,4.5,12,SEGAR,1` → telemetri `kamera:true`; tunggu 4 s → `kamera:false` dan field null;
  `TXXXXXXXX…` (120 karakter) lalu `1` → baris dibuang, alarm tetap menyala. Pantau topik dengan MQTT client (mis. MQTTX/Node-RED debug).
- [ ] **Step 5: Commit** `feat(esp32): parser baris serial, telemetri 1 Hz, status LWT`.

### Task 6: Firmware — perintah, level, eskalasi, waktu respons

**Files:**
- Modify: `esp32/sketch.ino`

**Interfaces:**
- Consumes: `levelTerakhir` (Task 5).
- Produces: event `log` JSON (`jenis` alarm/reset/level/wajib_istirahat/kalibrasi_ditolak, `waktu`, `total_kantuk`, `durasi_alarm_s` untuk reset); subscribe `perintah`.

- [ ] **Step 1:** Callback MQTT: `KALIBRASI` → tulis `CMD,KALIBRASI\n` ke Serial kecuali `isAlarmActive || wajibIstirahat` (publish `kalibrasi_ditolak`); `TES_ALARM` → buzzer + LED merah 1000 ms non-blocking, tanpa ubah `isAlarmActive`/`totalPelanggaran`, diabaikan saat alarm.
- [ ] **Step 2:** Level naik ke LELAH/BAHAYA (bukan saat alarm): chirp 3× (100 ms bunyi/100 ms jeda, non-blocking), LED kuning berkedip 2 Hz selama level ≥ LELAH, OLED level + "ISTIRAHAT", publish `level`. Saat `kal` = 0 dari baris `T`, OLED menampilkan "KALIBRASI" (kecuali saat alarm).
- [ ] **Step 3:** Eskalasi: simpan waktu 2 alarm terakhir; ≥ 2 dalam 600000 ms → `wajibIstirahat` true, OLED "WAJIB ISTIRAHAT", publish event; reset otomatis 600000 ms setelah alarm terakhir. Reset tombol → publish `reset` dengan `durasi_alarm_s` (1 desimal).
- [ ] **Step 4: Verifikasi** (Wokwi/serial manual + MQTT client): publish `TES_ALARM` → bunyi 1 s, hitungan tetap; kirim `T,…,60,LELAH,1` → 3 chirp; `1`, tombol, `1` dalam 10 menit → OLED "WAJIB ISTIRAHAT"; saat alarm publish `KALIBRASI` → event `kalibrasi_ditolak`, tidak ada `CMD` di serial; putus WiFi lalu kirim level LELAH → chirp tetap. Cek sintaks seperti Task 5.
- [ ] **Step 5: Commit** `feat(esp32): perintah dashboard, peringatan level, eskalasi wajib istirahat`.

### Task 7: Flow Node-RED + dashboard

**Files:**
- Create: `nodered/flows.json`
- Create: `nodered/uji_publish.js` (publish contoh ke broker untuk uji flow; dijalankan dengan `NODE_PATH=%USERPROFILE%\.node-red\node_modules node nodered/uji_publish.js`)

**Interfaces:**
- Consumes: topik MQTT Task 5–6.

- [ ] **Step 1:** Flow: `mqtt in` (`telemetri`, `log`, `status`) → `json` → function tambah `diterima` → `mongodb out` (`deteksi_kantuk`, insert, only payload); `ui_button` Kalibrasi ulang/Tes alarm → `mqtt out` `perintah`.
- [ ] **Step 2:** Tab `Monitoring Pengemudi` sesuai sketsa spec 5.6: teks status perangkat (online/offline/kamera terputus; watchdog `trigger` 5 s), `ui_gauge` skor dengan sektor 30/55/80, teks level + saran (pemetaan level → saran memakai teks Global Constraints), `ui_chart` EAR + ambang (2 menit), `ui_chart` skor & PERCLOS (30 menit; isi awal dari `mongodb in` find `diterima` ≥ now-30 menit saat UI dibuka), angka total hari ini (`mongodb in` count `jenis:"alarm"` sejak 00.00, diperbarui saat ada event), total sejak alat menyala, ambang & baseline, `ui_table`/`ui_template` 10 kejadian terakhir, `ui_toast` untuk alarm dan wajib istirahat, banner merah wajib istirahat.
- [ ] **Step 3: Verifikasi:** import ke Node-RED lokal, deploy, jalankan `uji_publish.js` (telemetri 10× + log alarm + status offline) → semua widget berubah, dokumen masuk `deteksi_kantuk.telemetri`/`kejadian` (cek di Compass), status OFFLINE muncul; hentikan publish 6 s → "OFFLINE". Hapus database uji setelahnya.
- [ ] **Step 4: Commit** `feat(nodered): dashboard monitoring pengemudi + penyimpanan MongoDB`.

### Task 8: README dan skenario demo

**Files:**
- Create: `README.md`

- [ ] **Step 1:** Tulis: arsitektur singkat, cara pasang (pip, model, Arduino library, import flow, MongoDB), cara menjalankan, protokol serial & topik MQTT, penjelasan tiga fitur smart dengan rumus dan bobot, keterbatasan (broker publik tanpa TLS, GPIO 12), dan skenario demo 5 menit: kalibrasi dua orang → ambang berbeda; mata sayu → skor naik dan chirp sebelum microsleep; tutup mata 3 s → alarm + tombol + waktu respons; dua alarm → wajib istirahat; tombol Tes alarm & Kalibrasi ulang dari dashboard; cabut WiFi → alarm tetap jalan, dashboard OFFLINE.
- [ ] **Step 2:** Jalankan seluruh tes: `cd python && python -m unittest -v` → semua PASS.
- [ ] **Step 3: Commit** `docs: README dan skenario demo`.
