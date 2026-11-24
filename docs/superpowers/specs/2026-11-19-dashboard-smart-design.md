# Desain: Dashboard Monitoring + Fitur Smart (Deteksi Kantuk Kelompok 8)

Tanggal: 2026-11-19 · Basis kode: branch `feat/dashboard-smart` (dicabang dari `fix/wiring-mqtt-oled`, PR #1)

## 1. Maksud dan alasan

Dosen menilai demo final project dari empat hal minimal: **input**, **output**, **koneksi internet**, dan
**dashboard monitoring**. Dashboard adalah bagian terpenting. Selain itu bagian **"smart"** harus jelas, karena itu
yang dibanggakan saat demo. Syarat dari kelompok: **perangkat IoT (ESP32) tetap menjadi pusat sistem**, bukan
sekadar laptop.

Kondisi sekarang: input (webcam EAR, tombol) dan output (buzzer, LED, relay, OLED) sudah ada. Koneksi internet
lemah (ESP32 hanya mengirim satu pesan teks saat alarm). Dashboard belum ada. "Smart" baru berupa aturan tetap
`EAR < 0,25 selama 2 detik`.

## 2. Tujuan, non-tujuan, anti-tujuan

**Tujuan**
- G1. Tiga fitur smart yang bisa didemokan dan dijelaskan dalam satu kalimat masing-masing:
  1. **Kalibrasi otomatis per pengemudi** — ambang EAR dipelajari dari mata pengemudi sendiri.
  2. **Skor kelelahan prediktif (0–100)** — memberi peringatan *sebelum* microsleep.
  3. **Eskalasi "wajib istirahat" di perangkat** — ESP32 sendiri mendeteksi alarm berulang.
- G2. ESP32 menjadi gerbang internet: mengirim telemetri 1 Hz, log kejadian, status online/offline, dan menerima
  perintah dari dashboard.
- G3. Dashboard Node-RED yang menampilkan data live, riwayat (MongoDB), dan tombol perintah ke alat.
- G4. Jalur keselamatan lokal (`'0'/'W'/'1'` → aktuator) tidak berubah dan tetap bekerja tanpa internet.

**Non-tujuan**
- Telegram Bot, banyak pengemudi/armada sekaligus (cukup satu perangkat; `device` tetap ada di payload),
  aplikasi mobile, model machine learning, hosting Node-RED di cloud (Node-RED jalan di laptop `localhost:1880`;
  data tetap melewati internet karena broker-nya publik).
- TLS/autentikasi broker (dicatat sebagai keterbatasan, sesuai makalah subbab 5.7).

**Anti-tujuan (gagal walau "jalan")**
- Fitur smart membuat alarm microsleep lebih lambat atau tidak andal.
- Dashboard/internet masuk ke jalur keselamatan (alarm bergantung pada broker atau Node-RED).
- Dashboard bisa **mematikan alarm dari jauh**. Alarm hanya mati lewat tombol fisik (konfirmasi pengemudi sadar).
- Data dummy saat demo. Semua angka di dashboard berasal dari sensor/webcam sungguhan.

## 3. Batasan

- Perangkat: ESP32 DevKit V1, rangkaian sesuai `wokwi/diagram.json` versi PR #1. Pin tidak berubah.
- Serial USB 115200 bps adalah satu-satunya jalur laptop ↔ ESP32.
- Broker: `broker.hivemq.com:1883` (publik, tanpa akun) — sama dengan kode sekarang.
- Laptop demo sudah memiliki Node-RED dengan palet `node-red-dashboard@3.6.6` dan `node-red-node-mongodb@0.2.5`,
  serta MongoDB 9.0 sebagai service di `localhost:27017`.
- Python: tidak menambah dependensi selain yang ada (`opencv-python`, `mediapipe`, `pyserial`).
- `main.py` belum pernah dijalankan dengan webcam di laptop demo. Laptop demo memakai **Python 3.14**; wheel
  MediaPipe untuk Python ini hanya tersedia mulai 0.10.30 (versi 0.10.21 terakhir untuk ≤ 3.12), dan paket baru
  tersebut kemungkinan tidak lagi memuat API lama `mp.solutions.face_mesh` yang dipakai `main.py` sekarang.
- Wokwi tidak punya webcam; uji alur penuh dilakukan di perangkat fisik. Wokwi tetap dipakai untuk uji firmware
  dengan mengetik baris serial manual.

## 4. Pendekatan yang dipertimbangkan

| | Pendekatan | Kelebihan | Kekurangan |
|---|---|---|---|
| **A (dipilih)** | Laptop menghitung fitur smart, kirim ringkasan 1 Hz lewat serial; **ESP32 meneruskan ke MQTT** dan menerima perintah | ESP32 benar-benar perangkat IoT yang online, dimonitor, dan dikontrol; jalur keselamatan tetap lokal | Protokol serial jadi dua arah; ada parsing di kedua sisi |
| B | Python publish telemetri langsung pakai `paho-mqtt`; ESP32 hanya alarm | Paling sederhana | ESP32 hampir tidak berperan sebagai IoT; poin "koneksi internet" melemah |
| C | Python kirim EAR mentah, skor dihitung di Node-RED | Logika terpusat | Bertentangan dengan konsep edge computing di makalah; bergantung jaringan |

Kelompok memilih **A** dengan alasan: "intinya harus tetap ada perangkat IoT yang digunakan".

## 5. Desain

### 5.1 Arsitektur

```
Webcam → main.py (EAR, kalibrasi, skor) ──serial 115200──► ESP32 ──WiFi/MQTT──► broker.hivemq.com ──► Node-RED ──► Dashboard
            ▲   '0'/'W'/'1' (kritis)     T,... (1 Hz)        │  aktuator lokal                                  │
            └──────────── CMD,... ◄──────────────────────────┘◄──────────── perintah dari dashboard ◄───────────┘ MongoDB
```

### 5.2 Deteksi wajah: MediaPipe Tasks FaceLandmarker

`mp.solutions.face_mesh` diganti `mediapipe.tasks.python.vision.FaceLandmarker` (mode `VIDEO`, 1 wajah). API ini
tersedia di MediaPipe 0.10.x maupun 1.x, sehingga aman apa pun versi yang terpasang. Keluarannya tetap 478
landmark dengan indeks yang sama, jadi `MATA_KIRI`, `MATA_KANAN`, dan `hitung_ear()` tidak berubah. Model
`face_landmarker.task` (±3,6 MB, Apache 2.0) diunduh sekali lalu disimpan di repo (`python/models/`), sehingga demo
tidak bergantung pada unduhan saat berjalan. `requirements.txt` dikunci ke versi yang lolos uji di laptop demo.

Alternatif yang ditolak: memasang Python 3.12 terpisah dan mengunci `mediapipe==0.10.21` agar `mp.solutions`
tetap ada. Ditolak karena menambah instalasi Python kedua di laptop demo dan mengunci proyek ke versi lama.

### 5.3 Fitur smart

**(1) Kalibrasi otomatis per pengemudi** — di `main.py`
- Saat program mulai (dan saat perintah kalibrasi), kumpulkan EAR dari frame yang wajahnya terdeteksi selama
  **10 detik**. Pengemudi diminta menatap kamera normal (teks instruksi di jendela video, OLED "KALIBRASI").
- `baseline = median(sampel)` (median tahan terhadap kedipan).
- `ambang = clamp(0,75 × baseline, 0,15, 0,30)`.
- Sebelum kalibrasi pertama selesai, pakai ambang bawaan 0,25. Bila sampel < 50 frame (wajah sering hilang),
  kalibrasi dianggap gagal dan diulang, maksimal 3 kali; setelah itu ambang terakhir tetap dipakai dan status
  `kal` = 2 (gagal) dikirim ke dashboard.
- **Selama kalibrasi ulang** (perintah dari dashboard), deteksi microsleep tetap berjalan dengan **ambang lama**;
  ambang baru baru dipakai setelah kalibrasi sukses. Perintah `KALIBRASI` **ditolak oleh ESP32** selama alarm aktif
  atau `wajib_istirahat` aktif, agar pengemudi yang mengantuk tidak dikalibrasi sebagai "normal".
- Demo: dua orang berbeda → ambang berbeda tampil di dashboard.

**(2) Skor kelelahan prediktif** — di `main.py`, dihitung tiap 1 detik dari jendela bergulir
- `PERCLOS60` = persentase frame 60 detik terakhir dengan EAR < ambang.
- `tutup_panjang_5m` = jumlah episode mata tertutup ≥ 1 detik dalam 5 menit terakhir.
- `microsleep_10m` = jumlah episode mata tertutup ≥ 2 detik (dihitung sekali per episode, saat episode dimulai
  melewati 2 detik) dalam 10 menit terakhir. Ini sengaja **berbeda** dari hitungan alarm ESP32: alarm ESP32
  tertahan (_latched_) sampai tombol ditekan, sehingga satu alarm bisa memuat lebih dari satu episode. Dashboard
  memberi label berbeda ("Episode microsleep 10 mnt" vs "Alarm"), dan protokol serial tidak perlu jalur balik status.
- Rumus awal (bobot boleh disetel builder setelah uji, asalkan tetap dijelaskan di README):
  `skor = 60·min(PERCLOS60/0,30, 1) + 25·min(tutup_panjang_5m/3, 1) + 15·min(microsleep_10m/2, 1)`, dibulatkan 0–100.
- Selama kalibrasi pertama belum selesai, skor tidak dihitung (dikirim `-1`).
- Level: 0–29 **SEGAR** · 30–54 **WASPADA** · 55–79 **LELAH** · 80–100 **BAHAYA**.
- Saran teks per level (contoh: LELAH → "Disarankan istirahat 15 menit").
- Aksi di perangkat saat level **naik** ke LELAH/BAHAYA (bukan alarm penuh): OLED menampilkan level dan
  "ISTIRAHAT", buzzer berbunyi pendek 3× (chirp), LED kuning berkedip. Inilah sisi *prediktif*: peringatan muncul
  sebelum microsleep terjadi.

**(3) Eskalasi "wajib istirahat"** — dihitung **di ESP32**
- ESP32 menyimpan waktu (`millis`) alarm terakhir. Jika ≥ 2 alarm dalam 10 menit → `wajib_istirahat = true`.
- Efek: OLED "WAJIB ISTIRAHAT", event MQTT, banner merah di dashboard. Status hilang otomatis setelah 10 menit
  tanpa alarm.
- **Waktu respons pengemudi**: ESP32 mengukur lama alarm berbunyi sampai tombol ditekan dan mengirimnya di event
  `reset` (metrik tambahan yang murah dan informatif).

### 5.4 Protokol serial v2 (laptop ↔ ESP32)

Laptop → ESP32:
- Karakter tunggal `'0'`, `'W'`, `'1'` — **tidak berubah**, tetap jalur kritis, diproses segera.
- Baris telemetri 1 Hz: `T,<ear>,<ambang>,<baseline>,<perclos>,<skor>,<level>,<kal>\n`
  contoh `T,0.312,0.234,0.312,4.5,12,SEGAR,1\n` (`kal`: 0 = sedang kalibrasi, 1 = selesai, 2 = gagal; `ear` = -1
  bila wajah tidak terdeteksi).
  Huruf `T` tidak bentrok dengan `'0'/'W'/'1'`; ESP32 mengumpulkan karakter sampai `\n`.

ESP32 → laptop:
- `CMD,KALIBRASI\n` (diteruskan dari dashboard). Python membaca serial secara non-blocking setiap frame dan
  mengabaikan baris lain (pesan debug firmware).

### 5.5 MQTT (prefix `kelompok8/deteksi_kantuk/`)

| Topik | Arah | Isi | QoS/retain |
|---|---|---|---|
| `telemetri` | ESP32 → broker | JSON 1 Hz dari **timer ESP32 sendiri**: `device, waktu, kamera, ear, ambang, baseline, perclos, skor, level, kalibrasi, alarm, total_kantuk, wajib_istirahat, rssi`. `kamera` = true bila baris `T` diterima ≤ 3 detik terakhir; bila false, field dari laptop dikirim `null` | 0 / tidak |
| `log` | ESP32 → broker | JSON kejadian: `jenis` = `alarm` / `reset` (+`durasi_alarm_s`) / `level` / `wajib_istirahat`, `waktu`, `total_kantuk` | 0 / tidak |
| `status` | ESP32 → broker | `online` saat terhubung; Last Will `offline` | 1 / retain |
| `perintah` | dashboard → ESP32 | `KALIBRASI` atau `TES_ALARM` | 0 / tidak |

`TES_ALARM`: buzzer + LED merah 1 detik lalu kembali normal; **tidak** menambah hitungan, tidak masuk keadaan ALARM.
Tidak ada perintah untuk mematikan alarm (anti-tujuan).

### 5.6 Node-RED dan dashboard

Flow disimpan di repo sebagai `nodered/flows.json` (bisa di-import). Node-RED subscribe ke tiga topik, menyimpan
`telemetri` dan `log` ke MongoDB (`localhost:27017`, database `deteksi_kantuk`, collection `telemetri` dan
`kejadian`, `msg.payload` saja + `diterima` = waktu server), dan mem-publish `perintah`.

Tampilan `http://localhost:1880/ui`, tab **Monitoring Pengemudi**:

```
┌ Perangkat: ● ONLINE  RSSI -58 dBm  update 1 s lalu ┬ [ WAJIB ISTIRAHAT ] (banner merah bila aktif) ┐
├ Gauge SKOR KELELAHAN 0–100 (warna level) ─────────┼ Level: LELAH · Saran: istirahat 15 menit ───────┤
├ Grafik live EAR + garis ambang (2 menit) ─────────────────────────────────────────────────────────────┤
├ Grafik skor & PERCLOS (30 menit, dari MongoDB saat dibuka + live) ─────────────────────────────────────┤
├ Total kantuk hari ini: 3 │ Alarm: AKTIF/tidak │ Ambang pribadi: 0,234 (baseline 0,312) ──────────────┤
├ Tabel 10 kejadian terakhir (waktu, jenis, total, durasi respons) ─────────────────────────────────────┤
└ [ Kalibrasi ulang ]  [ Tes alarm ]                    notifikasi pop-up saat alarm / wajib istirahat ┘
```

Status perangkat OFFLINE muncul dari Last Will atau bila tidak ada telemetri > 5 detik. Bila ESP32 online tetapi
`kamera` = false, dashboard menampilkan "Perangkat ONLINE · kamera/laptop TERPUTUS" (alarm lokal tetap siaga).

"Total kantuk hari ini" = jumlah event `alarm` di collection `kejadian` sejak pukul 00.00 (query MongoDB). Angka
`total_kantuk` dari ESP32 ditampilkan terpisah sebagai "sejak alat menyala" (sama dengan OLED).

Palet `node-red-node-mongodb@0.2.5` (driver 3.7.4) sudah diuji insert ke MongoDB 9.0.4 di laptop ini: berhasil.

### 5.7 Berkas yang berubah

- `python/main.py` — FaceLandmarker (Tasks API), kalibrasi, skor, jendela bergulir, baris `T`, baca `CMD`. Logika murni (kalibrasi, PERCLOS,
  skor, level) dipisah ke modul kecil yang bisa diuji tanpa kamera.
- `esp32/sketch.ino` — parsing baris, publish telemetri/log/status (LWT), subscribe perintah, eskalasi, waktu
  respons, tampilan OLED level/kalibrasi, chirp. Jalur `'0'/'W'/'1'` dan urutan aktuator → OLED → MQTT tetap.
- `nodered/flows.json` — flow + dashboard (baru).
- `python/models/face_landmarker.task` (baru) dan `python/requirements.txt` (versi dikunci).
- `README.md` — cara menjalankan dan skenario demo (baru).

## 6. Diputuskan oleh kelompok

- Fitur smart: skor kelelahan prediktif sebagai fitur utama, kalibrasi otomatis sebagai fondasi, ditambah
  perintah dari dashboard ke alat.
- Pendekatan A: ESP32 tetap perangkat IoT yang online dan dikontrol.

## 7. Diputuskan oleh penyusun desain (boleh dikoreksi)

- Node-RED Dashboard v1 (sudah terpasang, sesuai materi praktikum) + MongoDB untuk riwayat.
- Broker publik HiveMQ (sudah dipakai kode, demo tanpa akun).
- Angka awal: kalibrasi 10 detik, ambang 0,75 × baseline dibatasi 0,15–0,30, jendela 60 detik/5 menit/10 menit,
  bobot skor 60/25/15, batas level 30/55/80, eskalasi 2 alarm/10 menit.
- Tidak ada reset alarm dari jarak jauh.
- ESP32 mem-publish telemetri dengan timer sendiri dan flag `kamera`, sehingga gangguan laptop tidak terlihat
  sebagai perangkat offline.
- Kalibrasi ulang memakai ambang lama sampai sukses, maksimal 3 percobaan, dan ditolak saat alarm/wajib istirahat.
- Skor memakai episode microsleep versi Python (bukan hitungan alarm ESP32); label di dashboard dibedakan.
- Field `baseline` ditambahkan ke baris `T` dan JSON telemetri.
- "Total kantuk hari ini" dihitung dari MongoDB; hitungan ESP32 ditampilkan sebagai "sejak alat menyala".
- Deteksi wajah pindah ke MediaPipe Tasks FaceLandmarker; model disimpan di repo.
- Wi-Fi demo: SSID/password dijadikan konstanta di bagian atas `sketch.ino` (bawaan tetap `Wokwi-GUEST`).

## 8. Diserahkan ke builder

- Struktur internal kode (nama fungsi, pembagian modul), selama logika murni bisa diuji tanpa kamera.
- Tata letak detail widget dashboard dan warna, selama isi bagian 5.6 terpenuhi.
- Penyetelan bobot skor setelah uji nyata, dengan alasan dicatat di README.
- Skrip/skenario uji (minimal: uji unit skor/kalibrasi dengan data sintetis, uji firmware dengan baris serial
  manual, uji flow Node-RED dengan publish MQTT manual).
