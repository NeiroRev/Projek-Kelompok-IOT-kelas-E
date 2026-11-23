#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <WiFi.h>
#include <PubSubClient.h>

// --- PEMETAAN PIN SESUAI RANGKAIAN ---
#define SDA_PIN    21
#define SCL_PIN    22
#define BUZZER_PIN 25
#define LED_HIJAU  26
#define LED_KUNING 27
#define LED_MERAH  14
#define RELAY1_PIN 12  // IN1 - Simulasi Lampu Hazard
#define BUTTON_PIN 4   // Tombol Reset Fisik (INPUT_PULLUP)

// --- LOGIKA RELAY (ACTIVE-LOW) ---
// Jika nanti saat kondisi "FOKUS" relay malah menyala, tukar LOW dan HIGH di bawah ini.
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH

// --- KONFIGURASI OLED 0.96" ---
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// --- KONFIGURASI WIFI & MQTT CLOUD ---
const char* ssid        = "iot";      // Ganti dengan SSID WiFi 2.4GHz
const char* password    = "akuganteng";  // Ganti dengan Password WiFi
const char* mqtt_server = "broker.hivemq.com";
const char* mqtt_topic  = "kelompok8/deteksi_kantuk/log";

WiFiClient espClient;
PubSubClient client(espClient);

// --- VARIABEL STATE MACHINE ---
bool isAlarmActive = false;
int totalPelanggaran = 0;
unsigned long lastReconnectAttempt = 0;

void tampilkanOLED(const char* baris1, const char* baris2, int ukuranTeks) {
  display.clearDisplay();
  display.setTextColor(WHITE);
  display.setTextSize(ukuranTeks);
  display.setCursor(0, 10);
  display.println(baris1);

  if (strlen(baris2) > 0) {
    display.setTextSize(1);
    display.setCursor(0, 42);
    display.print(baris2);
  }
  display.display();
}

void setNormalState() {
  isAlarmActive = false;
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_MERAH, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(RELAY1_PIN, RELAY_OFF);
  digitalWrite(LED_HIJAU, HIGH);

  String info = "Total Kantuk: " + String(totalPelanggaran);
  tampilkanOLED("  FOKUS", info.c_str(), 2);
}

void setAlarmState() {
  if (isAlarmActive) return;
  isAlarmActive = true;
  totalPelanggaran++;

  // Eksekusi Aktuator Lokal (Jalur Kritis)
  digitalWrite(LED_HIJAU, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(LED_MERAH, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  digitalWrite(RELAY1_PIN, RELAY_ON);

  String info = "Pelanggaran ke-" + String(totalPelanggaran);
  tampilkanOLED("BAHAYA:\nMENGANTUK!", info.c_str(), 1);

  // Kirim Log ke Cloud (Jalur Non-Kritis)
  if (client.connected()) {
    String payload = "{\"status\":\"MENGANTUK\",\"total_kantuk\":" + String(totalPelanggaran) + ",\"uptime_ms\":" + String(millis()) + "}";
    client.publish(mqtt_topic, payload.c_str());
    Serial.println("Log terkirim ke MQTT.");
  } else {
    Serial.println("MQTT offline - Alarm lokal tetap berjalan.");
  }
}

void reconnectMQTTNonBlocking() {
  if (WiFi.status() != WL_CONNECTED) return;

  unsigned long now = millis();
  if (now - lastReconnectAttempt > 5000) {
    lastReconnectAttempt = now;
    String clientId = "ESP32_Kel8_" + String(random(0xffff), HEX);
    if (client.connect(clientId.c_str())) {
      Serial.println("MQTT Terhubung!");
      lastReconnectAttempt = 0;
    }
  }
}

void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_HIJAU, OUTPUT);
  pinMode(LED_KUNING, OUTPUT);
  pinMode(LED_MERAH, OUTPUT);
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Matikan buzzer & relay saat mulai
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY1_PIN, RELAY_OFF);

  Wire.begin(SDA_PIN, SCL_PIN);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println(F("Gagal inisialisasi OLED! Cek kabel SDA/SCL."));
    for (;;);
  }

  WiFi.begin(ssid, password);
  client.setServer(mqtt_server, 1883);

  setNormalState();
  Serial.println("Sistem Edge ESP32 Siap.");
}

void loop() {
  // 1. Baca Sinyal Serial dari Laptop (Python)
  if (Serial.available() > 0) {
    char dataMasuk = Serial.read();

    if (dataMasuk == '1') {
      setAlarmState();
    } else if (dataMasuk == 'W' && !isAlarmActive) {
      digitalWrite(LED_KUNING, HIGH);
    } else if (dataMasuk == '0' && !isAlarmActive) {
      digitalWrite(LED_KUNING, LOW);
    }
  }

  // 2. Cek Tombol Reset Fisik
  if (digitalRead(BUTTON_PIN) == LOW && isAlarmActive) {
    delay(50);
    if (digitalRead(BUTTON_PIN) == LOW) {
      setNormalState();
      Serial.println("Alarm direset oleh pengemudi.");
      while (digitalRead(BUTTON_PIN) == LOW) {
        delay(10);
      }
    }
  }

  // 3. Jaga Koneksi MQTT secara Non-Blocking
  if (!client.connected()) {
    reconnectMQTTNonBlocking();
  } else {
    client.loop();
  }
}