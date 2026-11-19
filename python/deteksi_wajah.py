import math

import cv2
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

# Indeks titik area kelopak mata (P1..P6), sama dengan Face Mesh lama: 478 landmark berindeks sama
MATA_KIRI = [33, 160, 158, 133, 153, 144]
MATA_KANAN = [362, 385, 387, 263, 373, 380]


def buat_landmarker(path_model):
    opsi = FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=path_model),
                                 running_mode=RunningMode.VIDEO, num_faces=1)
    return FaceLandmarker.create_from_options(opsi)


def deteksi(landmarker, frame_bgr, t_ms):
    """Kembalikan 478 landmark ternormalisasi wajah pertama, atau None bila tidak ada wajah.
    t_ms harus naik terus (syarat mode VIDEO)."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    hasil = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), t_ms)
    return hasil.face_landmarks[0] if hasil.face_landmarks else None


def hitung_jarak(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)


def hitung_ear(titik_mata, landmarks, w, h):
    pts = [(int(landmarks[p].x * w), int(landmarks[p].y * h)) for p in titik_mata]
    # Vertikal
    v1 = hitung_jarak(pts[1], pts[5])
    v2 = hitung_jarak(pts[2], pts[4])
    # Horizontal
    horizontal = hitung_jarak(pts[0], pts[3])

    if horizontal == 0.0: return 0.0
    return (v1 + v2) / (2.0 * horizontal)
