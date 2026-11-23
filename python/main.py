import os
import urllib.request
import cv2
import math
import time
import serial
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

# --- KONFIGURASI SERIAL ESP32 ---
PORT_SERIAL = 'COM9'  # Sesuaikan dengan Port ESP32 di Arduino IDE
BAUD_RATE = 115200

try:
    esp = serial.Serial(PORT_SERIAL, BAUD_RATE, timeout=1)
    time.sleep(2)
    print(f"[OK] Terhubung ke ESP32 di {PORT_SERIAL}")
except Exception as e:
    esp = None
    print(f"[WARNING] Mode Uji Coba tanpa ESP32 (Gagal buka {PORT_SERIAL}: {e})")

# --- UNDUH MODEL FACE LANDMARKER OTOMATIS (SEKALI SAJA) ---
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task")
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

if not os.path.exists(MODEL_PATH):
    print("[INFO] Mengunduh model face_landmarker.task (~3.7 MB)...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("[OK] Model berhasil diunduh.")

# --- INISIALISASI MEDIAPIPE TASKS (FACE LANDMARKER) ---
base_options = python.BaseOptions(model_asset_path=MODEL_PATH)
options = vision.FaceLandmarkerOptions(
    base_options=base_options,
    num_faces=1,
    min_face_detection_confidence=0.5,
    min_face_presence_confidence=0.5,
    min_tracking_confidence=0.5
)
detector = vision.FaceLandmarker.create_from_options(options)

# Indeks 6 titik landmark mata (P1 sampai P6)
MATA_KIRI  = [33, 160, 158, 133, 153, 144]
MATA_KANAN = [362, 385, 387, 263, 373, 380]

# --- PARAMETER DETEKSI (SESUAI LAPORAN) ---
BATAS_EAR     = 0.25  # Rentang kalibrasi 0.21 - 0.25
DURASI_AWAL   = 1.0   # Detik -> Peringatan dini (LED Kuning)
DURASI_BAHAYA = 2.0   # Detik -> Bahaya mengantuk (Alarm)

waktu_mulai_tutup = None
status_terakhir = None

def kirim_serial(karakter):
    global status_terakhir
    if esp and karakter != status_terakhir:
        esp.write(karakter.encode())
        status_terakhir = karakter

def hitung_jarak(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def hitung_ear(titik_mata, landmarks, w, h):
    pts = [(int(landmarks[p].x * w), int(landmarks[p].y * h)) for p in titik_mata]
    v1 = hitung_jarak(pts[1], pts[5])
    v2 = hitung_jarak(pts[2], pts[4])
    horizontal = hitung_jarak(pts[0], pts[3])

    if horizontal == 0.0:
        return 0.0
    return (v1 + v2) / (2.0 * horizontal)

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("[ERROR] Webcam tidak dapat dibuka.")
    exit()

print("Kamera aktif. Tekan tombol 'q' pada jendela video untuk keluar.")

while cap.isOpened():
    ret, frame = cap.read()
    if not ret:
        break

    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    hasil = detector.detect(mp_image)

    if hasil.face_landmarks:
        for face_landmarks in hasil.face_landmarks:
            ear_kiri = hitung_ear(MATA_KIRI, face_landmarks, w, h)
            ear_kanan = hitung_ear(MATA_KANAN, face_landmarks, w, h)
            rata_ear = (ear_kiri + ear_kanan) / 2.0

            if rata_ear < BATAS_EAR:
                if waktu_mulai_tutup is None:
                    waktu_mulai_tutup = time.time()

                durasi = time.time() - waktu_mulai_tutup

                if durasi >= DURASI_BAHAYA:
                    cv2.putText(frame, "STATUS: BAHAYA MENGANTUK!", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                    kirim_serial('1')
                elif durasi >= DURASI_AWAL:
                    cv2.putText(frame, f"STATUS: PERINGATAN ({durasi:.1f}s)", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    kirim_serial('W')
                else:
                    cv2.putText(frame, "STATUS: BERKEDIP", (20, 40),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            else:
                waktu_mulai_tutup = None
                cv2.putText(frame, "STATUS: FOKUS", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                kirim_serial('0')

            cv2.putText(frame, f"EAR: {rata_ear:.2f}", (20, 80),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    else:
        waktu_mulai_tutup = None
        cv2.putText(frame, "Wajah tidak terdeteksi", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (200, 200, 200), 2)

    cv2.imshow("Deteksi Kantuk Pengemudi - Kelompok 8", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

detector.close()
cap.release()
cv2.destroyAllWindows()
if esp:
    esp.close()