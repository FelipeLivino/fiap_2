#include <DHT.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#define MQTT_MAX_PACKET_SIZE 1024
#include <PubSubClient.h>

// AstroWater AI - simulacao IoT no Wokwi.
// O loop principal usa agendamento por millis(), sem delay bloqueante.
// Em falha de rede, as medicoes ficam em um ring buffer em RAM.

const int PH_PIN = 34;
const int TURBIDITY_PIN = 35;
const int HARDNESS_PIN = 32;
const int SOLIDS_PIN = 33;
const int CHLORAMINES_PIN = 36;
const int SULFATE_PIN = 39;
const int CONDUCTIVITY_PIN = 4;
const int ORGANIC_CARBON_PIN = 13;
const int TRIHALOMETHANES_PIN = 12;
const int DHT_PIN = 15;
#define DHT_TYPE DHT22
const int NETWORK_SWITCH_PIN = 16;
const int LED_GREEN_PIN = 25;
const int LED_YELLOW_PIN = 26;
const int LED_RED_PIN = 27;
const int BUZZER_PIN = 14;

const bool LED_ACTIVE_HIGH = true;
const bool ENABLE_SERIAL_LOG = true;
const bool ENABLE_SERIAL_JSON = false;
const bool ENABLE_MQTT = true;

const char* DEVICE_ID = "ASTRO-ESP32-001";
const char* COMMUNITY = "Comunidade Aurora";
const char* WIFI_SSID = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* MQTT_BROKER = "broker.emqx.io";
const int MQTT_PORT = 1883;
const char* MQTT_CLIENT_ID_PREFIX = "astrowater-esp32";
const char* MQTT_TOPIC = "fiap/astrowater/readings";

const unsigned long SENSOR_INTERVAL_MS = 5000;
const unsigned long NETWORK_INTERVAL_MS = 500;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;
const unsigned long MQTT_RETRY_INTERVAL_MS = 5000;
const size_t PAYLOAD_BUFFER_SIZE = 1024;
const uint8_t MEASUREMENT_QUEUE_SIZE = 20;
const int RAW_CONDUCTIVITY_FALLBACK = 1726;
const int RAW_ORGANIC_CARBON_FALLBACK = 1880;
const int RAW_TRIHALOMETHANES_FALLBACK = 2188;

DHT dht(DHT_PIN, DHT_TYPE);
LiquidCrystal_I2C lcd(0x27, 16, 2);
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

enum RiskLevel {
  RISK_GREEN = 1,
  RISK_YELLOW = 2,
  RISK_ORANGE = 3,
  RISK_RED = 4
};

struct SensorReading {
  int rawPh;
  int rawTurbidity;
  int rawHardness;
  int rawSolids;
  int rawChloramines;
  int rawSulfate;
  int rawConductivity;
  int rawOrganicCarbon;
  int rawTrihalomethanes;
  float ph;
  float turbidity;
  float temperature;
  float hardness;
  float solids;
  float chloramines;
  float sulfate;
  float conductivity;
  float organicCarbon;
  float trihalomethanes;
  float mlTurbidity;
  RiskLevel risk;
};

struct CachedPayload {
  char payload[PAYLOAD_BUFFER_SIZE];
};

CachedPayload measurementQueue[MEASUREMENT_QUEUE_SIZE];
uint8_t queueHead = 0;
uint8_t queueCount = 0;
unsigned long lastSensorRead = 0;
unsigned long lastNetworkTick = 0;
unsigned long lastWifiAttempt = 0;
unsigned long lastMqttAttempt = 0;
bool previousNetworkEnabled = true;

float mapFloat(int raw, float inMin, float inMax, float outMin, float outMax) {
  return (raw - inMin) * (outMax - outMin) / (inMax - inMin) + outMin;
}

void logLine(const String& message) {
  if (ENABLE_SERIAL_LOG) {
    Serial.println(message);
  }
}

void writeLed(int pin, bool enabled) {
  digitalWrite(pin, enabled == LED_ACTIVE_HIGH ? HIGH : LOW);
}

bool isNetworkSwitchOn() {
  return digitalRead(NETWORK_SWITCH_PIN) == HIGH;
}

int readAdc2WithWifiFallback(int pin, int fallbackRaw) {
  int raw = analogRead(pin);
  if (ENABLE_MQTT && isNetworkSwitchOn() && WiFi.status() == WL_CONNECTED && raw <= 8) {
    logLine("[ADC2] GPIO" + String(pin) + " retornou 0 com WiFi ativo. Usando fallback simulado.");
    return fallbackRaw;
  }
  return raw;
}

RiskLevel maxRisk(RiskLevel current, RiskLevel candidate) {
  return candidate > current ? candidate : current;
}

RiskLevel classifyPh(float ph) {
  if (ph < 6.0 || ph > 9.0) {
    return RISK_RED;
  }
  if (ph < 6.5 || ph > 8.5) {
    return RISK_YELLOW;
  }
  return RISK_GREEN;
}

RiskLevel classifyTurbidity(float turbidity) {
  if (turbidity > 50.0) {
    return RISK_RED;
  }
  if (turbidity > 25.0) {
    return RISK_ORANGE;
  }
  if (turbidity > 5.0) {
    return RISK_YELLOW;
  }
  return RISK_GREEN;
}

RiskLevel classifyTemperature(float temperature) {
  if (temperature > 35.0) {
    return RISK_ORANGE;
  }
  if (temperature < 5.0 || temperature > 30.0) {
    return RISK_YELLOW;
  }
  return RISK_GREEN;
}

const char* riskToText(RiskLevel risk) {
  switch (risk) {
    case RISK_GREEN:
      return "verde";
    case RISK_YELLOW:
      return "amarelo";
    case RISK_ORANGE:
      return "laranja";
    case RISK_RED:
      return "vermelho";
    default:
      return "desconhecido";
  }
}

String riskCause(const SensorReading& reading) {
  if (reading.ph < 6.0) return "pH baixo";
  if (reading.ph > 9.0) return "pH alto";
  if (reading.turbidity > 50.0) return "Tb alta";
  if (reading.turbidity > 25.0) return "Tb elev";
  if (reading.temperature > 35.0) return "Temp alta";
  if (reading.ph < 6.5 || reading.ph > 8.5) return "pH atencao";
  if (reading.turbidity > 5.0) return "Tb atencao";
  if (reading.temperature < 5.0 || reading.temperature > 30.0) return "Temp atencao";
  return "OK";
}

SensorReading readSensors() {
  SensorReading reading;
  reading.rawPh = analogRead(PH_PIN);
  reading.rawTurbidity = analogRead(TURBIDITY_PIN);
  reading.rawHardness = analogRead(HARDNESS_PIN);
  reading.rawSolids = analogRead(SOLIDS_PIN);
  reading.rawChloramines = analogRead(CHLORAMINES_PIN);
  reading.rawSulfate = analogRead(SULFATE_PIN);
  reading.rawConductivity = readAdc2WithWifiFallback(
    CONDUCTIVITY_PIN,
    RAW_CONDUCTIVITY_FALLBACK
  );
  reading.rawOrganicCarbon = readAdc2WithWifiFallback(
    ORGANIC_CARBON_PIN,
    RAW_ORGANIC_CARBON_FALLBACK
  );
  reading.rawTrihalomethanes = readAdc2WithWifiFallback(
    TRIHALOMETHANES_PIN,
    RAW_TRIHALOMETHANES_FALLBACK
  );

  float dhtTemperature = dht.readTemperature();

  reading.ph = mapFloat(reading.rawPh, 0.0, 4095.0, 0.0, 14.0);
  reading.turbidity = mapFloat(reading.rawTurbidity, 0.0, 4095.0, 0.0, 100.0);
  reading.temperature = isnan(dhtTemperature) ? 25.0 : dhtTemperature;
  reading.hardness = mapFloat(reading.rawHardness, 0.0, 4095.0, 47.0, 323.0);
  reading.solids = mapFloat(reading.rawSolids, 0.0, 4095.0, 320.0, 61227.0);
  reading.chloramines = mapFloat(reading.rawChloramines, 0.0, 4095.0, 0.35, 13.13);
  reading.sulfate = mapFloat(reading.rawSulfate, 0.0, 4095.0, 129.0, 481.0);
  reading.conductivity = mapFloat(reading.rawConductivity, 0.0, 4095.0, 181.0, 753.0);
  reading.organicCarbon = mapFloat(reading.rawOrganicCarbon, 0.0, 4095.0, 2.2, 28.3);
  reading.trihalomethanes = mapFloat(reading.rawTrihalomethanes, 0.0, 4095.0, 0.74, 124.0);
  reading.mlTurbidity = mapFloat(reading.rawTurbidity, 0.0, 4095.0, 1.45, 6.74);

  RiskLevel risk = RISK_GREEN;
  risk = maxRisk(risk, classifyPh(reading.ph));
  risk = maxRisk(risk, classifyTurbidity(reading.turbidity));
  risk = maxRisk(risk, classifyTemperature(reading.temperature));
  reading.risk = risk;

  return reading;
}

void updateOutputs(RiskLevel risk) {
  writeLed(LED_GREEN_PIN, risk == RISK_GREEN);
  writeLed(LED_YELLOW_PIN, risk == RISK_YELLOW || risk == RISK_ORANGE);
  writeLed(LED_RED_PIN, risk == RISK_RED);

  if (risk == RISK_RED) {
    tone(BUZZER_PIN, 1200, 250);
  } else {
    noTone(BUZZER_PIN);
  }
}

String buildJson(const SensorReading& reading) {
  String payload = "{";
  payload += "\"deviceId\":\"" + String(DEVICE_ID) + "\",";
  payload += "\"community\":\"" + String(COMMUNITY) + "\",";
  payload += "\"rawPh\":" + String(reading.rawPh) + ",";
  payload += "\"rawTurbidity\":" + String(reading.rawTurbidity) + ",";
  payload += "\"rawHardness\":" + String(reading.rawHardness) + ",";
  payload += "\"rawSolids\":" + String(reading.rawSolids) + ",";
  payload += "\"rawChloramines\":" + String(reading.rawChloramines) + ",";
  payload += "\"rawSulfate\":" + String(reading.rawSulfate) + ",";
  payload += "\"rawConductivity\":" + String(reading.rawConductivity) + ",";
  payload += "\"rawOrganicCarbon\":" + String(reading.rawOrganicCarbon) + ",";
  payload += "\"rawTrihalomethanes\":" + String(reading.rawTrihalomethanes) + ",";
  payload += "\"ph\":" + String(reading.ph, 2) + ",";
  payload += "\"turbidity\":" + String(reading.turbidity, 2) + ",";
  payload += "\"temperature\":" + String(reading.temperature, 2) + ",";
  payload += "\"Hardness\":" + String(reading.hardness, 2) + ",";
  payload += "\"Solids\":" + String(reading.solids, 2) + ",";
  payload += "\"Chloramines\":" + String(reading.chloramines, 2) + ",";
  payload += "\"Sulfate\":" + String(reading.sulfate, 2) + ",";
  payload += "\"Conductivity\":" + String(reading.conductivity, 2) + ",";
  payload += "\"Organic_carbon\":" + String(reading.organicCarbon, 2) + ",";
  payload += "\"Trihalomethanes\":" + String(reading.trihalomethanes, 2) + ",";
  payload += "\"Turbidity\":" + String(reading.mlTurbidity, 2) + ",";
  payload += "\"mlTurbidity\":" + String(reading.mlTurbidity, 2) + ",";
  payload += "\"edgeRisk\":\"" + String(riskToText(reading.risk)) + "\",";
  payload += "\"networkSwitch\":\"" + String(isNetworkSwitchOn() ? "ON" : "OFF") + "\",";
  payload += "\"source\":\"wokwi-esp32\"";
  payload += "}";
  return payload;
}

void updateDisplay(const SensorReading& reading) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("pH ");
  lcd.print(reading.ph, 1);
  lcd.print(" Tb ");
  lcd.print(reading.turbidity, 0);

  lcd.setCursor(0, 1);
  lcd.print(riskToText(reading.risk));
  lcd.print(" ");
  lcd.print(riskCause(reading));
}

void enqueueMeasurement(const String& payload) {
  uint8_t index = (queueHead + queueCount) % MEASUREMENT_QUEUE_SIZE;

  if (queueCount == MEASUREMENT_QUEUE_SIZE) {
    queueHead = (queueHead + 1) % MEASUREMENT_QUEUE_SIZE;
    queueCount--;
    logLine("[CACHE] Ring buffer cheio. Medicao antiga descartada.");
    index = (queueHead + queueCount) % MEASUREMENT_QUEUE_SIZE;
  }

  payload.toCharArray(measurementQueue[index].payload, PAYLOAD_BUFFER_SIZE);
  queueCount++;
  logLine("[CACHE] Medicao salva na RAM (" + String(queueCount) + "/" + String(MEASUREMENT_QUEUE_SIZE) + ").");
}

bool peekOldestPayload(String& payload) {
  if (queueCount == 0) {
    return false;
  }
  payload = String(measurementQueue[queueHead].payload);
  return true;
}

void removeOldestPayload() {
  if (queueCount == 0) {
    return;
  }
  queueHead = (queueHead + 1) % MEASUREMENT_QUEUE_SIZE;
  queueCount--;
}

void connectWifiIfNeeded() {
  if (!isNetworkSwitchOn()) {
    return;
  }
  if (!ENABLE_MQTT) {
    return;
  }
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();
  if (lastWifiAttempt != 0 && now - lastWifiAttempt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }

  lastWifiAttempt = now;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  logLine("[WIFI] Tentando conectar...");
}

bool connectMqttIfNeeded() {
  if (!isNetworkSwitchOn() || !ENABLE_MQTT || WiFi.status() != WL_CONNECTED) {
    return false;
  }
  if (mqttClient.connected()) {
    return true;
  }

  unsigned long now = millis();
  if (lastMqttAttempt != 0 && now - lastMqttAttempt < MQTT_RETRY_INTERVAL_MS) {
    return false;
  }

  lastMqttAttempt = now;
  String clientId = String(MQTT_CLIENT_ID_PREFIX) + "-" + String(random(0xffff), HEX);
  bool connected = mqttClient.connect(clientId.c_str());
  logLine(connected ? "[MQTT] Conectado." : "[MQTT] Falha ao conectar.");
  return connected;
}

bool publishMqtt(const String& payload) {
  if (!ENABLE_MQTT || !connectMqttIfNeeded()) {
    return false;
  }

  bool published = mqttClient.publish(MQTT_TOPIC, payload.c_str());
  logLine(published ? "[MQTT] Medicao enviada." : "[MQTT] Falha no publish.");
  return published;
}

void processPendingMeasurements() {
  if (queueCount == 0) {
    return;
  }
  if (!isNetworkSwitchOn()) {
    return;
  }
  if (!ENABLE_MQTT) {
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  String payload;
  if (!peekOldestPayload(payload)) {
    return;
  }

  if (publishMqtt(payload)) {
    removeOldestPayload();
    logLine("[SYNC] Medicao removida da fila. Pendentes: " + String(queueCount));
  }
}

void collectMeasurement() {
  SensorReading reading = readSensors();
  updateOutputs(reading.risk);
  updateDisplay(reading);

  String payload = buildJson(reading);
  if (ENABLE_SERIAL_JSON) {
    logLine(payload);
  } else {
    logLine(
      "[STATUS] pH=" + String(reading.ph, 2)
      + " Tb=" + String(reading.turbidity, 1)
      + " risco=" + riskToText(reading.risk)
      + " rede=" + String(isNetworkSwitchOn() ? "ON" : "OFF")
      + " fila=" + String(queueCount)
    );
    logLine(
      "[ML] Hardness=" + String(reading.hardness, 1)
      + " Solids=" + String(reading.solids, 0)
      + " Chloramines=" + String(reading.chloramines, 2)
      + " Sulfate=" + String(reading.sulfate, 1)
      + " Conductivity=" + String(reading.conductivity, 1)
      + " Organic_carbon=" + String(reading.organicCarbon, 2)
      + " Trihalomethanes=" + String(reading.trihalomethanes, 1)
      + " TurbidityML=" + String(reading.mlTurbidity, 2)
    );
  }
  enqueueMeasurement(payload);
}

void handleNetworkSwitch() {
  bool networkEnabled = isNetworkSwitchOn();
  if (networkEnabled == previousNetworkEnabled) {
    return;
  }

  previousNetworkEnabled = networkEnabled;
  if (networkEnabled) {
    logLine("[WIFI] Switch ON. Rede liberada; tentando sincronizar fila.");
    lastWifiAttempt = 0;
    lastMqttAttempt = 0;
    return;
  }

  if (mqttClient.connected()) {
    mqttClient.disconnect();
  }
  if (WiFi.status() == WL_CONNECTED) {
    WiFi.disconnect(false);
  }
  logLine("[WIFI] Switch OFF. Rede simulada indisponivel; medicoes ficarao no cache.");
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("[INFO] AstroWater AI serial iniciado.");

  pinMode(LED_GREEN_PIN, OUTPUT);
  pinMode(LED_YELLOW_PIN, OUTPUT);
  pinMode(LED_RED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(NETWORK_SWITCH_PIN, INPUT_PULLUP);
  previousNetworkEnabled = isNetworkSwitchOn();

  dht.begin();
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("AstroWater AI");
  lcd.setCursor(0, 1);
  lcd.print("Wokwi ESP32");

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setBufferSize(PAYLOAD_BUFFER_SIZE);

  logLine("[INFO] Sistema pronto. Cache RAM max " + String(MEASUREMENT_QUEUE_SIZE) + " medicoes.");
  logLine("[INFO] Switch WiFi inicial: " + String(previousNetworkEnabled ? "ON" : "OFF"));
  collectMeasurement();
}

void loop() {
  unsigned long now = millis();

  handleNetworkSwitch();
  connectWifiIfNeeded();
  if (isNetworkSwitchOn() && WiFi.status() == WL_CONNECTED && ENABLE_MQTT) {
    mqttClient.loop();
  }

  if (now - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = now;
    collectMeasurement();
  }

  if (now - lastNetworkTick >= NETWORK_INTERVAL_MS) {
    lastNetworkTick = now;
    processPendingMeasurements();
  }
}
