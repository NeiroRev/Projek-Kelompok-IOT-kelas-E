import os
import cv2
import serial
import time

from deteksi_wajah import MATA_KANAN, MATA_KIRI, buat_landmarker, deteksi, hitung_ear

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

# Threshold Laporan
BATAS_EAR = 0.25 
DURASI_BAHAYA = 2.0  # (Detik) Mata tertutup lebih dari 2 detik = Alarm
DURASI_AWAL = 1.0    # (Detik) Mata tertutup > 1 detik = Peringatan Kuning
waktu_mulai_tutup = None

cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    h, w, _ = frame.shape
    wajah = deteksi(landmarker, frame, int(time.monotonic() * 1000))

    if wajah:
        for face_landmarks in [wajah]:
            ear_kiri = hitung_ear(MATA_KIRI, face_landmarks, w, h)
            ear_kanan = hitung_ear(MATA_KANAN, face_landmarks, w, h)
            rata_ear = (ear_kiri + ear_kanan) / 2.0

            if rata_ear < BATAS_EAR:
                if waktu_mulai_tutup is None:
                    waktu_mulai_tutup = time.time()
                else:
                    durasi = time.time() - waktu_mulai_tutup
                    
                    if durasi >= DURASI_BAHAYA:
                        cv2.putText(frame, "STATUS: BAHAYA MICRO-SLEEP", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                        if esp: esp.write(b'1') # Trigger alarm
                    
                    elif durasi >= DURASI_AWAL:
                        cv2.putText(frame, "STATUS: Peringatan Dini", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                        if esp: esp.write(b'W') # Trigger LED Kuning
            else:
                waktu_mulai_tutup = None
                cv2.putText(frame, "STATUS: FOKUS", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                if esp: esp.write(b'0') # Reset sinyal peringatan

            cv2.putText(frame, f"Nilai EAR: {rata_ear:.2f}", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    else:
        # Wajah hilang (menunduk/keluar frame): reset timer agar durasi tidak "melompat" saat wajah kembali
        waktu_mulai_tutup = None
        cv2.putText(frame, "WAJAH TIDAK TERDETEKSI", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 165, 255), 2)

    cv2.imshow("Monitor Edge (Kelompok 8)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
if esp: esp.close()