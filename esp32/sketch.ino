#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <time.h>

// Pemetaan Pin (Sesuai Laporan)
#define SDA_PIN 21
#define SCL_PIN 22
#define BUZZER_PIN 25
#define LED_HIJAU 26
#define LED_KUNING 27
#define LED_MERAH 14
#define RELAY1_PIN 12 // Lampu Hazard
#define RELAY2_PIN 13 // Putus Gas
#define BUTTON_PIN 4  // Tombol Reset Fisik

// Konfigurasi Layar OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Konfigurasi WiFi & MQTT Cloud (ganti SSID/password sesuai hotspot saat demo fisik)
const char* WIFI_SSID = "Wokwi-GUEST"; // Pakai koneksi default Wokwi
const char* WIFI_PASS = "";
const char* mqtt_server = "broker.hivemq.com"; // Publik MQTT Broker untuk pengujian
const char* TOPIK_TELEMETRI = "kelompok8/deteksi_kantuk/telemetri";
const char* TOPIK_LOG = "kelompok8/deteksi_kantuk/log";
const char* TOPIK_STATUS = "kelompok8/deteksi_kantuk/status";

WiFiClient espClient;
PubSubClient client(espClient);

bool isAlarmActive = false;
bool oledOk = false;               // false = jalan terus tanpa layar, alarm tetap berfungsi
int totalPelanggaran = 0;
unsigned long lastReconnect = 0;   // jeda percobaan koneksi ulang MQTT
bool wajibIstirahat = false;

// Ringkasan 1 Hz dari laptop (baris "T,ear,ambang,baseline,perclos,skor,level,kal")
char bufBaris[96];
int pjgBaris = 0;
bool modeBaris = false;
unsigned long mulaiBaris = 0;
float tEar = -1, tAmbang = -1, tBaseline = -1, tPerclos = 0;
int tSkor = -1, tKal = 0;
char levelTerakhir[12] = "-";
unsigned long waktuBarisT = 0;
bool adaBarisT = false;
unsigned long lastTelemetri = 0;

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_HIJAU, OUTPUT);
  pinMode(LED_KUNING, OUTPUT);
  pinMode(LED_MERAH, OUTPUT);
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Amankan Relay saat boot
  digitalWrite(RELAY1_PIN, LOW);
  digitalWrite(RELAY2_PIN, LOW);

  Wire.begin(SDA_PIN, SCL_PIN);
  oledOk = display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  if(!oledOk) {
    // Jangan berhenti di sini: buzzer, LED, dan relay harus tetap bekerja walau layar rusak
    Serial.println(F("Gagal memuat OLED, lanjut tanpa layar"));
  }

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTime(7 * 3600, 0, "pool.ntp.org"); // Waktu kejadian dalam WIB (UTC+7)
  client.setServer(mqtt_server, 1883);
  client.setSocketTimeout(2); // Batasi blokir loop saat broker tidak terjangkau (bawaan 15 detik)
  client.setBufferSize(512);  // JSON telemetri > batas bawaan PubSubClient (256 byte)

  setNormalState();
}

void setNormalState() {
  isAlarmActive = false;
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_MERAH, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(RELAY1_PIN, LOW);
  digitalWrite(RELAY2_PIN, LOW);
  digitalWrite(LED_HIJAU, HIGH);

  if(!oledOk) return;
  display.clearDisplay();
  display.setTextSize(2);
  display.setTextColor(WHITE);
  display.setCursor(30, 25);
  display.println("FOKUS");
  display.display();
}

void setAlarmState() {
  if(isAlarmActive) return; // Cegah loop jika alarm sudah menyala
  isAlarmActive = true;
  totalPelanggaran++;

  digitalWrite(LED_HIJAU, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(LED_MERAH, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  digitalWrite(RELAY1_PIN, HIGH);
  digitalWrite(RELAY2_PIN, HIGH);

  if(oledOk) {
    display.clearDisplay();
    display.setTextSize(1);
    display.setTextColor(WHITE);
    display.setCursor(5, 10);
    display.println("BAHAYA: MENGANTUK!");
    display.setCursor(10, 35);
    display.print("Pelanggaran: ");
    display.println(totalPelanggaran);
    display.display();
  }

  // Pengiriman Log ke Cloud (setelah aktuator, boleh gagal tanpa mengganggu alarm)
  kirimLog();
}

void isiWaktu(char* waktu, size_t n) {
  // Timeout 0 ms: jangan menunggu NTP; jika belum sinkron kirim "belum-sinkron"
  snprintf(waktu, n, "belum-sinkron");
  struct tm info;
  if (getLocalTime(&info, 0)) {
    strftime(waktu, n, "%Y-%m-%dT%H:%M:%S", &info);
  }
}

void kirimLog() {
  if (!client.connected()) return;

  char waktu[20];
  isiWaktu(waktu, sizeof(waktu));
  char payload[96];
  snprintf(payload, sizeof(payload),
           "{\"device\":\"ESP32_Kel8\",\"waktu\":\"%s\",\"total_kantuk\":%d}",
           waktu, totalPelanggaran);
  client.publish(TOPIK_LOG, payload);
}

// Baris "T,..." dari laptop: 7 nilai setelah 'T'. Baris rusak/jumlah field salah diabaikan.
void prosesBaris(const char* isi) {
  float ear, ambang, baseline, perclos;
  int skor, kal, habis = 0;
  char level[12];
  int n = sscanf(isi, ",%f,%f,%f,%f,%d,%11[^,],%d%n", &ear, &ambang, &baseline, &perclos, &skor, level, &kal, &habis);
  if (n != 7 || isi[habis] != '\0') return;
  tEar = ear; tAmbang = ambang; tBaseline = baseline; tPerclos = perclos; tSkor = skor; tKal = kal;
  strncpy(levelTerakhir, level, sizeof(levelTerakhir) - 1);
  levelTerakhir[sizeof(levelTerakhir) - 1] = '\0';
  waktuBarisT = millis();
  adaBarisT = true;
}

// Angka dari laptop: -1 berarti "tidak ada" -> null di JSON
void angkaAtauNull(char* tujuan, size_t n, float nilai, int desimal) {
  if (nilai < 0) snprintf(tujuan, n, "null");
  else snprintf(tujuan, n, "%.*f", desimal, nilai);
}

void kirimTelemetri() {
  if (!client.connected()) return;

  bool kamera = adaBarisT && millis() - waktuBarisT <= 3000;
  char waktu[20], ear[12], ambang[12], baseline[12], perclos[12], skor[12], level[16], kal[8];
  isiWaktu(waktu, sizeof(waktu));
  if (kamera) {
    angkaAtauNull(ear, sizeof(ear), tEar, 3);
    angkaAtauNull(ambang, sizeof(ambang), tAmbang, 3);
    angkaAtauNull(baseline, sizeof(baseline), tBaseline, 3);
    angkaAtauNull(perclos, sizeof(perclos), tPerclos, 1);
    angkaAtauNull(skor, sizeof(skor), tSkor, 0);
    snprintf(level, sizeof(level), "\"%s\"", levelTerakhir);
    snprintf(kal, sizeof(kal), "%d", tKal);
  } else {
    // Laptop/kamera terputus: perangkat tetap online, data dari laptop dikosongkan
    strcpy(ear, "null"); strcpy(ambang, "null"); strcpy(baseline, "null"); strcpy(perclos, "null");
    strcpy(skor, "null"); strcpy(level, "null"); strcpy(kal, "null");
  }

  char payload[400];
  snprintf(payload, sizeof(payload),
           "{\"device\":\"ESP32_Kel8\",\"waktu\":\"%s\",\"kamera\":%s,\"ear\":%s,\"ambang\":%s,"
           "\"baseline\":%s,\"perclos\":%s,\"skor\":%s,\"level\":%s,\"kalibrasi\":%s,\"alarm\":%s,"
           "\"total_kantuk\":%d,\"wajib_istirahat\":%s,\"rssi\":%d}",
           waktu, kamera ? "true" : "false", ear, ambang, baseline, perclos, skor, level, kal,
           isAlarmActive ? "true" : "false", totalPelanggaran, wajibIstirahat ? "true" : "false", (int)WiFi.RSSI());
  client.publish(TOPIK_TELEMETRI, payload);
}

// Karakter kritis dari laptop ('0' / 'W' / '1'), perilakunya sama seperti sebelumnya
void prosesKarakterKritis(char dataMasuk) {
  if (dataMasuk == '1') {
    setAlarmState();
  } else if (dataMasuk == 'W' && !isAlarmActive) {
    digitalWrite(LED_HIJAU, LOW);
    digitalWrite(LED_KUNING, HIGH); // Indikator 1 detik awal
  } else if (dataMasuk == '0' && !isAlarmActive) {
    digitalWrite(LED_KUNING, LOW);  // Reset indikator kuning
    digitalWrite(LED_HIJAU, HIGH);
  }
}

void bacaSerial() {
  // Baris T yang tidak selesai dalam 50 ms (normalnya < 4 ms) dibuang agar karakter kritis tidak tertelan
  if (modeBaris && millis() - mulaiBaris > 50) modeBaris = false;

  int batas = 64; // proses paling banyak 64 byte per loop agar tombol tetap terbaca
  while (Serial.available() > 0 && batas-- > 0) {
    char c = Serial.read();
    if (!modeBaris) {
      if (c == 'T') {
        modeBaris = true;
        pjgBaris = 0;
        mulaiBaris = millis();
      } else {
        prosesKarakterKritis(c);
      }
    } else if (c == '\n') {
      bufBaris[pjgBaris] = '\0';
      prosesBaris(bufBaris);
      modeBaris = false;
    } else if (c != '\r') {
      if (pjgBaris < (int)sizeof(bufBaris) - 1) bufBaris[pjgBaris++] = c;
      else modeBaris = false; // baris terlalu panjang: buang
    }
  }
}

bool sambungMqtt() {
  // Last Will: broker mengumumkan "offline" bila ESP32 putus tidak normal
  if (!client.connect("ESP32_Kel8_Client", TOPIK_STATUS, 1, true, "offline")) return false;
  client.publish(TOPIK_STATUS, "online", true);
  return true;
}

void loop() {
  // 1. Eksekusi Jalur Kritis (Zero-Latency) + ringkasan 1 Hz dari laptop
  bacaSerial();

  // 2. Mekanisme Tombol Reset
  if (digitalRead(BUTTON_PIN) == LOW && isAlarmActive) {
    delay(50); // Debounce sederhana
    if (digitalRead(BUTTON_PIN) == LOW) {
      setNormalState();
      while(digitalRead(BUTTON_PIN) == LOW) { delay(10); } // Tunggu dilepas
    }
  }

  // 3. Jaga Koneksi Cloud di Latar Belakang (dicoba paling cepat tiap 5 detik agar loop tidak tertahan)
  if (!client.connected() && WiFi.status() == WL_CONNECTED && millis() - lastReconnect >= 5000) {
    lastReconnect = millis();
    sambungMqtt();
  }
  client.loop();

  // 4. Telemetri 1 Hz dari timer ESP32 sendiri (tetap jalan walau laptop/kamera mati)
  if (millis() - lastTelemetri >= 1000) {
    lastTelemetri = millis();
    kirimTelemetri();
  }
}