import os
import cv2
import serial
import time

from deteksi_wajah import MATA_KANAN, MATA_KIRI, buat_landmarker, deteksi, hitung_ear
from kelelahan import Kalibrator, PenilaiKelelahan, level_dari_skor, saran
from protokol import PembacaSerial, baris_telemetri

# --- KONFIGURASI SERIAL ---
# Ubah COM3 (Windows) atau /dev/ttyUSB0 (Linux/Mac) sesuai port ESP32 asli
PORT_SERIAL = 'COM3'
BAUD_RATE = 115200

try:
    esp = serial.Serial(PORT_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f"Berhasil terhubung ke ESP32 di port {PORT_SERIAL}")
except Exception as e:
    esp = None
    print(f"Warning: Mode Uji Coba tanpa ESP32 (Port {PORT_SERIAL} tidak terdeteksi)")

# --- INISIALISASI MEDIAPIPE (Tasks API FaceLandmarker, 478 landmark) ---
MODEL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'face_landmarker.task')
landmarker = buat_landmarker(MODEL)

# Threshold Laporan (ambang EAR kini dari kalibrasi otomatis, bawaan 0,25)
DURASI_BAHAYA = 2.0  # (Detik) Mata tertutup lebih dari 2 detik = Alarm
DURASI_AWAL = 1.0    # (Detik) Mata tertutup > 1 detik = Peringatan Kuning
waktu_mulai_tutup = None

# --- FITUR SMART ---
kalibrator = Kalibrator()          # ambang EAR pribadi
penilai = PenilaiKelelahan()       # skor kelelahan prediktif
pembaca = PembacaSerial()          # perintah dashboard yang diteruskan ESP32
t_telemetri = 0.0
skor, level = -1, '-'

FONT = cv2.FONT_HERSHEY_SIMPLEX
WARNA_LEVEL = {'SEGAR': (0, 255, 0), 'WASPADA': (0, 255, 255), 'LELAH': (0, 140, 255), 'BAHAYA': (0, 0, 255), '-': (200, 200, 200)}

cap = cv2.VideoCapture(0)
kalibrator.mulai(time.monotonic())

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    t = time.monotonic()
    h, w, _ = frame.shape
    wajah = deteksi(landmarker, frame, int(t * 1000))
    ambang = kalibrator.ambang  # selama kalibrasi ulang, ambang lama tetap dipakai
    rata_ear = None

    # 1. Jalur kritis: keputusan bahaya per frame (tidak berubah, hanya ambangnya pribadi)
    if wajah:
        ear_kiri = hitung_ear(MATA_KIRI, wajah, w, h)
        ear_kanan = hitung_ear(MATA_KANAN, wajah, w, h)
        rata_ear = (ear_kiri + ear_kanan) / 2.0

        if rata_ear < ambang:
            if waktu_mulai_tutup is None:
                waktu_mulai_tutup = t
            else:
                durasi = t - waktu_mulai_tutup

                if durasi >= DURASI_BAHAYA:
                    cv2.putText(frame, "STATUS: BAHAYA MICRO-SLEEP", (20, 40), FONT, 0.8, (0, 0, 255), 2)
                    if esp: esp.write(b'1') # Trigger alarm

                elif durasi >= DURASI_AWAL:
                    cv2.putText(frame, "STATUS: Peringatan Dini", (20, 40), FONT, 0.8, (0, 255, 255), 2)
                    if esp: esp.write(b'W') # Trigger LED Kuning
        else:
            waktu_mulai_tutup = None
            cv2.putText(frame, "STATUS: FOKUS", (20, 40), FONT, 0.8, (0, 255, 0), 2)
            if esp: esp.write(b'0') # Reset sinyal peringatan

        cv2.putText(frame, f"Nilai EAR: {rata_ear:.2f}", (20, 80), FONT, 0.6, (255, 255, 255), 1)
    else:
        # Wajah hilang (menunduk/keluar frame): reset timer agar durasi tidak "melompat" saat wajah kembali
        waktu_mulai_tutup = None
        cv2.putText(frame, "WAJAH TIDAK TERDETEKSI", (20, 40), FONT, 0.8, (0, 165, 255), 2)

    # 2. Fitur smart (jalur non-kritis, setelah karakter kritis frame ini terkirim)
    kalibrator.tambah(t, rata_ear)
    penilai.tambah(t, rata_ear, ambang)

    if esp and esp.in_waiting:
        for perintah in pembaca.masukkan(esp.read(esp.in_waiting)):
            if perintah == 'KALIBRASI':
                kalibrator.mulai(t)  # diabaikan bila kalibrasi sedang berjalan

    if t - t_telemetri >= 1.0:
        t_telemetri = t
        skor = penilai.skor(t, kalibrator.baseline is not None)
        level = level_dari_skor(skor)
        if esp:
            esp.write(baris_telemetri(rata_ear, ambang, kalibrator.baseline, penilai.perclos60(t), skor, level,
                                      kalibrator.status))

    baseline = f"{kalibrator.baseline:.3f}" if kalibrator.baseline is not None else "-"
    cv2.putText(frame, f"Ambang pribadi: {ambang:.3f} (baseline {baseline})", (20, 110), FONT, 0.6, (255, 255, 255), 1)
    cv2.putText(frame, f"Skor kelelahan: {skor if skor >= 0 else '-'}  {level}", (20, 140), FONT, 0.7, WARNA_LEVEL[level], 2)
    cv2.putText(frame, saran(level), (20, 170), FONT, 0.6, WARNA_LEVEL[level], 1)
    if kalibrator.berjalan:
        cv2.putText(frame, "KALIBRASI: tatap kamera dengan mata terbuka normal", (20, h - 20), FONT, 0.6, (255, 255, 0), 2)
    elif kalibrator.status == 2:
        cv2.putText(frame, "Kalibrasi gagal (wajah sering hilang). Tekan 'c' untuk ulang", (20, h - 20), FONT, 0.6, (0, 0, 255), 2)

    cv2.imshow("Monitor Edge (Kelompok 8)", frame)
    tombol = cv2.waitKey(1) & 0xFF
    if tombol == ord('q'):
        break
    if tombol == ord('c'):
        kalibrator.mulai(t)

cap.release()
cv2.destroyAllWindows()
if esp: esp.close()
