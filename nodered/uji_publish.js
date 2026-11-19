// Uji flow dashboard tanpa ESP32: kirim contoh telemetri, log, dan status ke broker.
// Jalankan (Windows):  set NODE_PATH=%APPDATA%\npm\node_modules\node-red\node_modules && node nodered\uji_publish.js
// Setelah uji, hapus data uji di MongoDB (database deteksi_kantuk) agar tidak tercampur data demo.
const mqtt = require('mqtt');

const PREFIX = 'kelompok8/deteksi_kantuk/';
const klien = mqtt.connect('mqtt://broker.hivemq.com:1883');
const tunggu = (ms) => new Promise((r) => setTimeout(r, ms));
// Format waktu lokal tanpa zona, sama seperti ESP32 (WIB)
const waktu = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 19);

function telemetri(i) {
  const skor = Math.min(100, i * 9);
  const level = skor < 30 ? 'SEGAR' : skor < 55 ? 'WASPADA' : skor < 80 ? 'LELAH' : 'BAHAYA';
  return {
    device: 'ESP32_Kel8', waktu: waktu(), kamera: true, ear: i % 4 === 0 ? 0.08 : 0.31, ambang: 0.234,
    baseline: 0.312, perclos: skor / 3, skor, level, kalibrasi: 1, alarm: i >= 9, total_kantuk: i >= 9 ? 1 : 0,
    wajib_istirahat: i >= 11, rssi: -58,
  };
}

klien.on('connect', async () => {
  console.log('terhubung ke broker');
  klien.publish(PREFIX + 'status', 'online', { qos: 1, retain: true });
  for (let i = 0; i < 12; i++) {
    klien.publish(PREFIX + 'telemetri', JSON.stringify(telemetri(i)));
    if (i === 6) klien.publish(PREFIX + 'log', JSON.stringify({ device: 'ESP32_Kel8', jenis: 'level', waktu: waktu(), total_kantuk: 0, level: 'LELAH' }));
    if (i === 9) klien.publish(PREFIX + 'log', JSON.stringify({ device: 'ESP32_Kel8', jenis: 'alarm', waktu: waktu(), total_kantuk: 1 }));
    if (i === 11) klien.publish(PREFIX + 'log', JSON.stringify({ device: 'ESP32_Kel8', jenis: 'reset', waktu: waktu(), total_kantuk: 1, durasi_alarm_s: 3.4 }));
    console.log('telemetri', i);
    await tunggu(1000);
  }
  // Satu telemetri dengan kamera terputus, lalu berhenti -> dashboard harus menulis OFFLINE setelah 5 detik
  klien.publish(PREFIX + 'telemetri', JSON.stringify({ ...telemetri(0), kamera: false, ear: null, ambang: null, baseline: null, perclos: null, skor: null, level: null, kalibrasi: null }));
  console.log('selesai; tunggu 6 detik lalu cek status OFFLINE di dashboard');
  await tunggu(500);
  klien.end();
});

klien.on('error', (e) => { console.error('gagal:', e.message); process.exit(1); });
