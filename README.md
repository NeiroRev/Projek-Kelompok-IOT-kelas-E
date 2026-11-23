# Sistem Deteksi Kantuk Pengemudi — Kelompok 8 Kelas E

Proyek akhir mata kuliah Internet of Things (CIT61026). Webcam mendeteksi mata tertutup, ESP32 membunyikan alarm
**tanpa bergantung internet**, lalu mengirim data ke dashboard monitoring lewat MQTT.

```
Webcam → laptop (main.py: EAR, kalibrasi, skor) ──Serial 115200──► ESP32 ──WiFi/MQTT──► broker.hivemq.com ──► Node-RED ──► Dashboard
            ▲          '0'/'W'/'1' (alarm) + baris T (1 Hz)          │ buzzer, LED, relay, OLED, tombol                 │
            └───────────────── CMD,KALIBRASI ◄─────────────────────────┘◄────────────── perintah dari dashboard ◄──────────┘ MongoDB
```

| Syarat dosen | Di proyek ini |
|---|---|
| Input | Webcam (EAR), tombol reset fisik, tombol di dashboard |
| Output | Buzzer, LED hijau/kuning/merah, relay hazard (GPIO 13) & pemutus gas (GPIO 32, opsional), OLED, notifikasi dashboard |
| Koneksi internet | ESP32 → MQTT: telemetri 1 Hz, log kejadian, status online/offline, menerima perintah |
| Monitoring dashboard | Node-RED Dashboard `http://localhost:1880/ui` + riwayat di MongoDB; ringkasan juga dikirim ke ThingsBoard Cloud |

## Fitur smart

1. **Kalibrasi otomatis per pengemudi** (`python/kelelahan.py` → `Kalibrator`). Pada 10 detik pertama, sistem
   mengukur EAR normal pengemudi. `baseline = median EAR`, `ambang = 0,75 × baseline` (dibatasi 0,15–0,30).
   Mata sipit tidak lagi memicu alarm palsu. Selama kalibrasi ulang, ambang lama tetap dipakai.
2. **Skor kelelahan prediktif 0–100** (`PenilaiKelelahan`). Setiap detik:
   `skor = 60·min(PERCLOS60/30%, 1) + 25·min(tutup ≥1 s dalam 5 menit / 3, 1) + 15·min(microsleep ≥2 s dalam 10 menit / 2, 1)`.
   Level: SEGAR < 30 ≤ WASPADA < 55 ≤ LELAH < 80 ≤ BAHAYA. Saat level naik ke LELAH/BAHAYA, alat berbunyi pendek
   3 kali, LED kuning berkedip, dan OLED menampilkan "ISTIRAHAT" — **sebelum** microsleep terjadi.
3. **Eskalasi "wajib istirahat" di ESP32**. Dua alarm dalam 10 menit → OLED "WAJIB ISTIRAHAT" dan banner merah di
   dashboard. ESP32 juga mengukur **waktu respons pengemudi** (lama alarm sampai tombol ditekan).

Alarm microsleep tetap aturan lama yang cepat (mata tertutup ≥ 2 detik, dengan ambang pribadi) dan hanya bisa
dimatikan lewat tombol fisik. Dashboard **tidak bisa** mematikan alarm.

## Struktur

| Berkas | Isi |
|---|---|
| `python/main.py` | Program utama di laptop |
| `python/deteksi_wajah.py` | MediaPipe Tasks FaceLandmarker (478 landmark) + EAR |
| `python/kelelahan.py` | Kalibrasi, PERCLOS, skor, level, saran (tanpa kamera, teruji) |
| `python/protokol.py` | Baris serial `T,...`, pembaca `CMD,...`, pengirim karakter kritis |
| `python/face_landmarker.task` | Model MediaPipe (Apache 2.0) |
| `esp32/PendeteksiKantukProjekAkhir/` | Firmware ESP32 lengkap (dashboard + fitur smart) — dipakai untuk demo |
| `esp32/PendeteksiKantukSederhana/` | Firmware versi Brian (ThingsBoard saja, tanpa fitur smart) — cadangan |
| `wokwi/diagram.json` | Rangkaian simulasi Wokwi |
| `nodered/flows.json` | Flow + dashboard Node-RED |
| `nodered/uji_publish.js` | Kirim data contoh ke broker untuk menguji dashboard tanpa ESP32 |
| `docs/superpowers/` | Desain dan rencana implementasi |

## Cara menjalankan

1. **Python** (diuji di Python 3.14):
   ```bash
   pip install -r python/requirements.txt
   ```
   Ubah `PORT_SERIAL` di `python/main.py` (bawaan `COM9`) sesuai port ESP32 di Arduino IDE. Tutup Serial Monitor
   Arduino IDE sebelum menjalankan `main.py`.
2. **ESP32**: buka `esp32/PendeteksiKantukProjekAkhir/PendeteksiKantukProjekAkhir.ino` di Arduino IDE, pasang
   library *Adafruit SSD1306*, *Adafruit GFX*, *PubSubClient*. Sesuaikan `WIFI_SSID`/`WIFI_PASS` (WiFi 2.4 GHz),
   lalu unggah ke *DOIT ESP32 DEVKIT V1*. Relay di-set **active-LOW** (`RELAY_ON LOW`) sesuai modul kelompok.
   Untuk Wokwi (`wokwi/diagram.json`): salin firmware ini, pakai WiFi `Wokwi-GUEST` tanpa password, dan tukar
   `RELAY_ON`/`RELAY_OFF` karena relay Wokwi active-HIGH.
3. **MongoDB** berjalan di `localhost:27017` (service MongoDB).
4. **Node-RED**: pasang palet `node-red-dashboard` dan `node-red-node-mongodb`, lalu *Import* `nodered/flows.json`
   dan *Deploy*. Buka `http://localhost:1880/ui`. Data tersimpan di database `deteksi_kantuk`
   (collection `telemetri` dan `kejadian`).
5. Jalankan `cd python && python main.py`. Tatap kamera normal selama 10 detik (kalibrasi). Tombol `c` = kalibrasi
   ulang, `q` = keluar.

Uji dashboard tanpa ESP32 (Windows):
```bash
set NODE_PATH=%APPDATA%\npm\node_modules\node-red\node_modules && node nodered\uji_publish.js
```
Hapus database `deteksi_kantuk` sesudahnya agar data uji tidak ikut saat demo.

Tes unit Python:
```bash
cd python && python -m unittest -v
```

## Protokol

Serial laptop → ESP32: karakter `'0'` (mata terbuka), `'W'` (tertutup ≥ 1 s), `'1'` (tertutup ≥ 2 s, alarm) —
dikirim saat status berubah dan diulang tiap 0,5 s — dan
setiap detik `T,<ear>,<ambang>,<baseline>,<perclos>,<skor>,<level>,<kal>` (`-1` = tidak ada; `kal` 0 sedang,
1 selesai, 2 gagal). ESP32 → laptop: `CMD,KALIBRASI`.

MQTT (`broker.hivemq.com:1883`, prefix `kelompok8/deteksi_kantuk/`):

| Topik | Arah | Isi |
|---|---|---|
| `telemetri` | ESP32 → | JSON 1 Hz: `kamera, ear, ambang, baseline, perclos, skor, level, kalibrasi, alarm, total_kantuk, wajib_istirahat, rssi, waktu` |
| `log` | ESP32 → | JSON `jenis`: `alarm`, `reset` (+`durasi_alarm_s`), `level`, `wajib_istirahat`, `kalibrasi_ditolak` |
| `status` | ESP32 → | `online` / Last Will `offline` (retain) |
| `perintah` | dashboard → | `KALIBRASI` (ditolak saat alarm/wajib istirahat) atau `TES_ALARM` |

ThingsBoard Cloud (`thingsboard.cloud:1883`, topik `v1/devices/me/telemetry`, username = token device): tiap 5 detik
dan saat alarm/reset, ESP32 mengirim `status` (FOKUS/MENGANTUK), `total_kantuk`, `uptime_ms`, `skor`, `level`,
`wajib_istirahat`, `kamera`.

## Skenario demo (± 5 menit)

1. **Kalibrasi dua orang**: orang A lalu orang B (tombol *Kalibrasi ulang* di dashboard) → ambang pribadi berbeda.
2. **Prediktif**: mata sayu/berkedip lama berulang → skor dan level naik di dashboard; saat LELAH, alat berbunyi
   pendek 3 kali **sebelum** ada microsleep.
3. **Microsleep**: tutup mata 3 detik → buzzer, LED merah, relay, OLED "BAHAYA"; tekan tombol → tabel kejadian
   menampilkan waktu respons.
4. **Eskalasi**: ulangi sekali lagi dalam 10 menit → "WAJIB ISTIRAHAT" di OLED dan banner merah di dashboard.
5. **Kontrol jarak jauh**: tombol *Tes alarm* di dashboard → alat berbunyi 1 detik.
6. **Edge computing**: matikan hotspot → dashboard OFFLINE dalam 5 detik, tetapi alarm di alat tetap bekerja.

## Keterbatasan

- Broker publik tanpa TLS/autentikasi: siapa pun yang tahu topik bisa membaca atau mengirim perintah. Untuk
  penerapan nyata gunakan broker privat dengan TLS dan ACL.
- Token ThingsBoard (`TB_TOKEN`) tersimpan di firmware pada repo publik; siapa pun yang membacanya bisa mengirim
  data ke device ThingsBoard kelompok. Buat ulang token setelah demo.
- Bobot skor adalah nilai awal dari desain; setel ulang setelah uji dengan beberapa responden.
