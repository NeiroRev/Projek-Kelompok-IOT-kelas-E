import cv2
import mediapipe as mp
import serial
import time
import math

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

# --- INISIALISASI MEDIAPIPE ---
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True)

# Indeks titik area kelopak mata
MATA_KIRI = [33, 160, 158, 133, 153, 144]
MATA_KANAN = [362, 385, 387, 263, 373, 380]

# Threshold Laporan
BATAS_EAR = 0.25 
DURASI_BAHAYA = 2.0  # (Detik) Mata tertutup lebih dari 2 detik = Alarm
DURASI_AWAL = 1.0    # (Detik) Mata tertutup > 1 detik = Peringatan Kuning
waktu_mulai_tutup = None

def hitung_jarak(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def hitung_ear(titik_mata, landmarks, w, h):
    pts = [(int(landmarks.landmark[p].x * w), int(landmarks.landmark[p].y * h)) for p in titik_mata]
    # Vertikal
    v1 = hitung_jarak(pts[1], pts[5])
    v2 = hitung_jarak(pts[2], pts[4])
    # Horizontal
    horizontal = hitung_jarak(pts[0], pts[3])
    
    if horizontal == 0.0: return 0.0
    return (v1 + v2) / (2.0 * horizontal)

cap = cv2.VideoCapture(0)

while cap.isOpened():
    ret, frame = cap.read()
    if not ret: break

    h, w, _ = frame.shape
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    hasil = face_mesh.process(rgb_frame)

    if hasil.multi_face_landmarks:
        for face_landmarks in hasil.multi_face_landmarks:
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

    cv2.imshow("Monitor Edge (Kelompok 8)", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
if esp: esp.close()