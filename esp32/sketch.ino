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

// Konfigurasi WiFi & MQTT Cloud
const char* ssid = "Wokwi-GUEST"; // Pakai koneksi default Wokwi
const char* password = "";
const char* mqtt_server = "broker.hivemq.com"; // Publik MQTT Broker untuk pengujian

WiFiClient espClient;
PubSubClient client(espClient);

bool isAlarmActive = false;
bool oledOk = false;               // false = jalan terus tanpa layar, alarm tetap berfungsi
int totalPelanggaran = 0;
unsigned long lastReconnect = 0;   // jeda percobaan koneksi ulang MQTT

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

  WiFi.begin(ssid, password);
  configTime(7 * 3600, 0, "pool.ntp.org"); // Waktu kejadian dalam WIB (UTC+7)
  client.setServer(mqtt_server, 1883);
  client.setSocketTimeout(2); // Batasi blokir loop saat broker tidak terjangkau (bawaan 15 detik)

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

void kirimLog() {
  if (!client.connected()) return;

  // Timeout 0 ms: jangan menunggu NTP; jika belum sinkron kirim "belum-sinkron"
  char waktu[20] = "belum-sinkron";
  struct tm info;
  if (getLocalTime(&info, 0)) {
    strftime(waktu, sizeof(waktu), "%Y-%m-%dT%H:%M:%S", &info);
  }

  char payload[96];
  snprintf(payload, sizeof(payload),
           "{\"device\":\"ESP32_Kel8\",\"waktu\":\"%s\",\"total_kantuk\":%d}",
           waktu, totalPelanggaran);
  client.publish("kelompok8/deteksi_kantuk/log", payload);
}

void loop() {
  // 1. Eksekusi Jalur Kritis (Zero-Latency)
  if (Serial.available() > 0) {
    char dataMasuk = Serial.read();
    
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
    client.connect("ESP32_Kel8_Client");
  }
  client.loop();
}