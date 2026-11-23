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
#define RELAY1_PIN 13 // Lampu Hazard (GPIO 13, aman dari strapping pin 12)
#define RELAY2_PIN 32 // Putus Gas (opsional; channel kedua relay bila dipasang)
#define BUTTON_PIN 4  // Tombol Reset Fisik

// Logika relay (modul fisik kelompok: ACTIVE-LOW). Di Wokwi relay active-HIGH: tukar LOW dan HIGH di bawah.
// Jika saat kondisi "FOKUS" relay malah menyala, tukar juga.
#define RELAY_ON   LOW
#define RELAY_OFF  HIGH

// Konfigurasi Layar OLED
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Konfigurasi WiFi & MQTT Cloud (WiFi 2.4 GHz; di Wokwi pakai "Wokwi-GUEST" tanpa password)
const char* WIFI_SSID = "iot";
const char* WIFI_PASS = "akuganteng";
const char* mqtt_server = "broker.hivemq.com"; // Publik MQTT Broker untuk pengujian
const char* TOPIK_TELEMETRI = "kelompok8/deteksi_kantuk/telemetri";
const char* TOPIK_LOG = "kelompok8/deteksi_kantuk/log";
const char* TOPIK_STATUS = "kelompok8/deteksi_kantuk/status";
const char* TOPIK_PERINTAH = "kelompok8/deteksi_kantuk/perintah";

// ThingsBoard Cloud (dashboard kedua dari Brian). Token = access token device di ThingsBoard.
const char* TB_SERVER = "thingsboard.cloud";
const char* TB_TOKEN = "GpBzDTPVZyoCU7rd7c0l";
const char* TB_TOPIK = "v1/devices/me/telemetry";
const unsigned long JEDA_TB = 5000UL;      // telemetri ringkas ke ThingsBoard tiap 5 detik

// Eskalasi: >= 2 alarm dalam 10 menit -> wajib istirahat (hilang 10 menit setelah alarm terakhir)
const unsigned long JENDELA_ESKALASI = 600000UL;

WiFiClient espClient;
PubSubClient client(espClient);
WiFiClient tbNet;                  // koneksi terpisah untuk ThingsBoard
PubSubClient tb(tbNet);
unsigned long lastReconnectTB = 2500; // digeser 2,5 s dari HiveMQ agar percobaan tidak bersamaan
unsigned long lastTB = 0;

bool isAlarmActive = false;
bool oledOk = false;               // false = jalan terus tanpa layar, alarm tetap berfungsi
int totalPelanggaran = 0;
unsigned long lastReconnect = 0;   // jeda percobaan koneksi ulang MQTT
bool wajibIstirahat = false;
unsigned long waktuAlarm[2] = {0, 0}; // dua alarm terakhir (millis), [1] paling baru
int jumlahAlarmTercatat = 0;
unsigned long mulaiAlarm = 0;      // untuk waktu respons pengemudi

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

// Peringatan prediktif (level LELAH/BAHAYA) dan tes alarm dari dashboard
int sisaChirp = 0;                 // jumlah pergantian buzzer tersisa (3 bunyi = 6)
unsigned long chirpBerikut = 0;
bool tesAktif = false;
unsigned long mulaiTes = 0;
int layarTampil = -1;              // isi OLED terakhir, agar tidak digambar ulang tiap detik

void terimaPerintah(char* topic, byte* payload, unsigned int length);
void setup() {
  Serial.begin(115200);

  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(LED_HIJAU, OUTPUT);
  pinMode(LED_KUNING, OUTPUT);
  pinMode(LED_MERAH, OUTPUT);
  pinMode(RELAY1_PIN, OUTPUT);
  pinMode(RELAY2_PIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  // Amankan buzzer & relay saat boot
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY1_PIN, RELAY_OFF);
  digitalWrite(RELAY2_PIN, RELAY_OFF);

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
  client.setCallback(terimaPerintah);
  tb.setServer(TB_SERVER, 1883);
  tb.setSocketTimeout(2);
  tb.setBufferSize(384);

  setNormalState();
}

// Data laptop dianggap basi bila tidak ada baris T selama > 3 detik (laptop/kamera terputus)
bool dataLaptopSegar() {
  return adaBarisT && millis() - waktuBarisT <= 3000;
}

// 0 SEGAR, 1 WASPADA, 2 LELAH, 3 BAHAYA, -1 belum ada skor
int peringkatLevel(const char* level) {
  if (strcmp(level, "SEGAR") == 0) return 0;
  if (strcmp(level, "WASPADA") == 0) return 1;
  if (strcmp(level, "LELAH") == 0) return 2;
  if (strcmp(level, "BAHAYA") == 0) return 3;
  return -1;
}

void tulisLayar(int ukuran, int x, int y, const char* baris1, const char* baris2) {
  display.clearDisplay();
  display.setTextSize(ukuran);
  display.setTextColor(WHITE);
  display.setCursor(x, y);
  display.println(baris1);
  if (baris2[0]) {
    display.setTextSize(1);
    display.setCursor(10, 50);
    display.println(baris2);
  }
  display.display();
}

// Isi OLED di luar alarm, urutan prioritas: wajib istirahat > kalibrasi > level lelah > fokus
void tampilkanLayar() {
  if (!oledOk || isAlarmActive) return;
  int peringkat = dataLaptopSegar() ? peringkatLevel(levelTerakhir) : -1;
  int pilihan; // 0 fokus, 1 lelah, 2 bahaya, 3 kalibrasi, 4 wajib istirahat
  if (wajibIstirahat) pilihan = 4;
  else if (dataLaptopSegar() && tKal == 0) pilihan = 3;
  else if (peringkat == 3) pilihan = 2;
  else if (peringkat == 2) pilihan = 1;
  else pilihan = 0;
  if (pilihan == layarTampil) return;
  layarTampil = pilihan;

  if (pilihan == 4) tulisLayar(2, 10, 10, "WAJIB\nISTIRAHAT", "2 alarm / 10 menit");
  else if (pilihan == 3) tulisLayar(2, 10, 20, "KALIBRASI", "Tatap kamera normal");
  else if (pilihan == 2) tulisLayar(2, 10, 10, "BAHAYA\nISTIRAHAT", "Segera menepi");
  else if (pilihan == 1) tulisLayar(2, 10, 10, "LELAH\nISTIRAHAT", "Istirahat 15 menit");
  else tulisLayar(2, 30, 25, "FOKUS", "");
}

void setNormalState() {
  isAlarmActive = false;
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(LED_MERAH, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(RELAY1_PIN, RELAY_OFF);
  digitalWrite(RELAY2_PIN, RELAY_OFF);
  digitalWrite(LED_HIJAU, HIGH);

  layarTampil = -1; // paksa gambar ulang setelah layar alarm
  tampilkanLayar();
  kirimThingsBoard();
}

void setAlarmState() {
  if(isAlarmActive) return; // Cegah loop jika alarm sudah menyala
  isAlarmActive = true;
  totalPelanggaran++;
  mulaiAlarm = millis();
  sisaChirp = 0;
  tesAktif = false;

  digitalWrite(LED_HIJAU, LOW);
  digitalWrite(LED_KUNING, LOW);
  digitalWrite(LED_MERAH, HIGH);
  digitalWrite(BUZZER_PIN, HIGH);
  digitalWrite(RELAY1_PIN, RELAY_ON);
  digitalWrite(RELAY2_PIN, RELAY_ON);

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
  kirimEvent("alarm", "");
  catatEskalasi();
  kirimThingsBoard();
}

// Eskalasi dihitung di perangkat: dua alarm dalam 10 menit
void catatEskalasi() {
  waktuAlarm[0] = waktuAlarm[1];
  waktuAlarm[1] = millis();
  if (jumlahAlarmTercatat < 2) jumlahAlarmTercatat++;
  if (jumlahAlarmTercatat == 2 && waktuAlarm[1] - waktuAlarm[0] <= JENDELA_ESKALASI && !wajibIstirahat) {
    wajibIstirahat = true;
    kirimEvent("wajib_istirahat", "");
  }
}

void isiWaktu(char* waktu, size_t n) {
  // Timeout 0 ms: jangan menunggu NTP; jika belum sinkron kirim "belum-sinkron"
  snprintf(waktu, n, "belum-sinkron");
  struct tm info;
  if (getLocalTime(&info, 0)) {
    strftime(waktu, n, "%Y-%m-%dT%H:%M:%S", &info);
  }
}

// Log kejadian: jenis alarm / reset / level / wajib_istirahat / kalibrasi_ditolak.
// `tambahan` = field JSON ekstra tanpa koma di depan (boleh kosong).
void kirimEvent(const char* jenis, const char* tambahan) {
  if (!client.connected()) return;

  char waktu[20];
  isiWaktu(waktu, sizeof(waktu));
  char payload[192];
  snprintf(payload, sizeof(payload),
           "{\"device\":\"ESP32_Kel8\",\"jenis\":\"%s\",\"waktu\":\"%s\",\"total_kantuk\":%d%s%s}",
           jenis, waktu, totalPelanggaran, tambahan[0] ? "," : "", tambahan);
  client.publish(TOPIK_LOG, payload);
}

// Peringatan prediktif saat level naik ke LELAH/BAHAYA: 3 bunyi pendek (bukan alarm penuh)
void cekKenaikanLevel(int sebelum, int sesudah) {
  if (sesudah < 2 || sesudah <= sebelum) return;
  char tambahan[32];
  snprintf(tambahan, sizeof(tambahan), "\"level\":\"%s\"", levelTerakhir);
  kirimEvent("level", tambahan);
  if (!isAlarmActive) {
    sisaChirp = 6;
    chirpBerikut = millis();
  }
}

// Baris "T,..." dari laptop: 7 nilai setelah 'T'. Baris rusak/jumlah field salah diabaikan.
void prosesBaris(const char* isi) {
  float ear, ambang, baseline, perclos;
  int skor, kal, habis = 0;
  char level[12];
  int n = sscanf(isi, ",%f,%f,%f,%f,%d,%11[^,],%d%n", &ear, &ambang, &baseline, &perclos, &skor, level, &kal, &habis);
  if (n != 7 || isi[habis] != '\0') return;
  int sebelum = peringkatLevel(levelTerakhir);
  tEar = ear; tAmbang = ambang; tBaseline = baseline; tPerclos = perclos; tSkor = skor; tKal = kal;
  strncpy(levelTerakhir, level, sizeof(levelTerakhir) - 1);
  levelTerakhir[sizeof(levelTerakhir) - 1] = '\0';
  waktuBarisT = millis();
  adaBarisT = true;
  cekKenaikanLevel(sebelum, peringkatLevel(levelTerakhir));
  tampilkanLayar();
}

// Angka dari laptop: -1 berarti "tidak ada" -> null di JSON
void angkaAtauNull(char* tujuan, size_t n, float nilai, int desimal) {
  if (nilai < 0) snprintf(tujuan, n, "null");
  else snprintf(tujuan, n, "%.*f", desimal, nilai);
}

void kirimTelemetri() {
  if (!client.connected()) return;

  bool kamera = dataLaptopSegar();
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

// Perintah dari dashboard. Tidak ada perintah untuk mematikan alarm: itu hanya lewat tombol fisik.
void terimaPerintah(char* /* topik: hanya satu topik yang di-subscribe */, uint8_t* isi, unsigned int panjang) {
  char perintah[24];
  unsigned int n = panjang < sizeof(perintah) - 1 ? panjang : sizeof(perintah) - 1;
  memcpy(perintah, isi, n);
  perintah[n] = '\0';

  if (strcmp(perintah, "KALIBRASI") == 0) {
    // Pengemudi yang sedang mengantuk tidak boleh dikalibrasi sebagai "normal"
    if (isAlarmActive || wajibIstirahat) kirimEvent("kalibrasi_ditolak", "");
    else Serial.print("CMD,KALIBRASI\n");
  } else if (strcmp(perintah, "TES_ALARM") == 0 && !isAlarmActive) {
    tesAktif = true;
    mulaiTes = millis();
    digitalWrite(BUZZER_PIN, HIGH);
    digitalWrite(LED_MERAH, HIGH);
  }
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

// Efek non-blocking: tes alarm 1 detik, chirp level, LED kuning berkedip saat LELAH/BAHAYA, akhir eskalasi
void perbaruiEfek() {
  unsigned long kini = millis();

  if (tesAktif && kini - mulaiTes >= 1000) {
    tesAktif = false;
    if (!isAlarmActive) {
      digitalWrite(BUZZER_PIN, LOW);
      digitalWrite(LED_MERAH, LOW);
    }
  }

  if (sisaChirp > 0 && (long)(kini - chirpBerikut) >= 0) {
    if (!isAlarmActive && !tesAktif) digitalWrite(BUZZER_PIN, sisaChirp % 2 == 0 ? HIGH : LOW);
    sisaChirp--;
    chirpBerikut += 100;
  }

  static bool berkedip = false;
  bool harusKedip = !isAlarmActive && dataLaptopSegar() && peringkatLevel(levelTerakhir) >= 2;
  if (harusKedip) {
    digitalWrite(LED_HIJAU, LOW);
    digitalWrite(LED_KUNING, (kini / 250) % 2 ? HIGH : LOW); // 2 Hz
  } else if (berkedip && !isAlarmActive) {
    // Level turun atau laptop terputus: kembali ke indikator normal
    digitalWrite(LED_KUNING, LOW);
    digitalWrite(LED_HIJAU, HIGH);
  }
  berkedip = harusKedip;

  if (wajibIstirahat && kini - waktuAlarm[1] >= JENDELA_ESKALASI) {
    wajibIstirahat = false;
  }
  tampilkanLayar(); // hanya menggambar bila isi layar berubah (mis. data laptop menjadi basi)
}

// Telemetri ringkas ke ThingsBoard. Kunci status/total_kantuk/uptime_ms sama dengan versi Brian,
// ditambah hasil fitur smart. Jalur non-kritis: gagal kirim tidak memengaruhi alarm.
void kirimThingsBoard() {
  if (!tb.connected()) return;
  char skor[12], level[16];
  if (dataLaptopSegar()) {
    angkaAtauNull(skor, sizeof(skor), tSkor, 0);
    snprintf(level, sizeof(level), "\"%s\"", levelTerakhir);
  } else {
    strcpy(skor, "null");
    strcpy(level, "null");
  }
  char payload[256];
  snprintf(payload, sizeof(payload),
           "{\"status\":\"%s\",\"total_kantuk\":%d,\"uptime_ms\":%lu,\"skor\":%s,\"level\":%s,"
           "\"wajib_istirahat\":%s,\"kamera\":%s}",
           isAlarmActive ? "MENGANTUK" : "FOKUS", totalPelanggaran, millis(), skor, level,
           wajibIstirahat ? "true" : "false", dataLaptopSegar() ? "true" : "false");
  tb.publish(TB_TOPIK, payload);
}

bool sambungThingsBoard() {
  // ThingsBoard: username = access token, password kosong
  String clientId = "ESP32_Kel8_TB_" + String(random(0xffff), HEX);
  return tb.connect(clientId.c_str(), TB_TOKEN, NULL);
}

bool sambungMqtt() {
  // Last Will: broker mengumumkan "offline" bila ESP32 putus tidak normal
  // Client ID acak: dua perangkat (mis. Wokwi + alat fisik) tidak saling memutus di broker publik
  String clientId = "ESP32_Kel8_" + String(random(0xffff), HEX);
  if (!client.connect(clientId.c_str(), TOPIK_STATUS, 1, true, "offline")) return false;
  client.publish(TOPIK_STATUS, "online", true);
  client.subscribe(TOPIK_PERINTAH);
  return true;
}

void loop() {
  // 1. Eksekusi Jalur Kritis (Zero-Latency) + ringkasan 1 Hz dari laptop
  bacaSerial();

  // 2. Mekanisme Tombol Reset
  if (digitalRead(BUTTON_PIN) == LOW && isAlarmActive) {
    delay(50); // Debounce sederhana
    if (digitalRead(BUTTON_PIN) == LOW) {
      float durasi = (millis() - mulaiAlarm) / 1000.0;
      setNormalState();
      char tambahan[32];
      snprintf(tambahan, sizeof(tambahan), "\"durasi_alarm_s\":%.1f", durasi);
      kirimEvent("reset", tambahan); // waktu respons pengemudi
      while(digitalRead(BUTTON_PIN) == LOW) { delay(10); } // Tunggu dilepas
    }
  }

  // 3. Efek peringatan prediktif, tes alarm, dan akhir eskalasi
  perbaruiEfek();

  // 4. Jaga Koneksi Cloud di Latar Belakang (dicoba paling cepat tiap 5 detik agar loop tidak tertahan)
  if (!client.connected() && WiFi.status() == WL_CONNECTED && millis() - lastReconnect >= 5000) {
    lastReconnect = millis();
    sambungMqtt();
  }
  client.loop();
  if (!tb.connected() && WiFi.status() == WL_CONNECTED && millis() - lastReconnectTB >= 5000) {
    lastReconnectTB = millis();
    sambungThingsBoard();
  }
  tb.loop();
  if (millis() - lastTB >= JEDA_TB) {
    lastTB = millis();
    kirimThingsBoard();
  }

  // 5. Telemetri 1 Hz dari timer ESP32 sendiri (tetap jalan walau laptop/kamera mati)
  if (millis() - lastTelemetri >= 1000) {
    lastTelemetri = millis();
    kirimTelemetri();
  }
}
