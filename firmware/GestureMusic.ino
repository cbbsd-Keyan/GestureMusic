#include <Wire.h>
#include <math.h>
#include <WiFi.h>
#include <WiFiUdp.h>

// ============================================================
// 引脚与地址
// ============================================================

const int SDA_PIN = 8;
const int SCL_PIN = 9;

const uint8_t MPU_ADDR = 0x68;

// ============================================================
// Wi-Fi
// ============================================================

const char* WIFI_SSID = "WIFI名";
const char* WIFI_PASSWORD = "WIFI密码";

const uint16_t UDP_PORT = 4210;

// 广播，电脑端不需要配置 IP
IPAddress broadcastIP(255, 255, 255, 255);

// 注册握手后记住电脑地址，切换为单播
// （广播无 ACK 不重传，热点下丢包严重）
IPAddress targetIP(0, 0, 0, 0);
bool hasTarget = false;

WiFiUDP udp;

// ============================================================
// Beat 检测参数（单位：deg/s）
// ============================================================

const float BEAT_THRESHOLD = 100.0;
const float CALIBRATION_THRESHOLD = 170.0;
const float RESET_THRESHOLD = 35.0;
const unsigned long COOLDOWN_MS = 220;

int beatDirection = 0;
bool beatArmed = true;
unsigned long lastBeatTime = 0;

unsigned long lastWifiCheck = 0;
unsigned long lastAliveTime = 0;

// ============================================================
// MPU 寄存器
// ============================================================

void writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(value);
  Wire.endTransmission();
}

bool readRegisters(uint8_t startReg, uint8_t* buffer, uint8_t length) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(startReg);

  if (Wire.endTransmission(false) != 0) {
    return false;
  }

  Wire.requestFrom(MPU_ADDR, length);

  if (Wire.available() != length) {
    return false;
  }

  for (uint8_t i = 0; i < length; i++) {
    buffer[i] = Wire.read();
  }

  return true;
}

uint8_t readRegister(uint8_t reg) {
  uint8_t value = 0;
  readRegisters(reg, &value, 1);
  return value;
}

void sendUDP(const String& message) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  IPAddress dest =
      hasTarget ? targetIP : broadcastIP;

  udp.beginPacket(dest, UDP_PORT);
  udp.print(message);
  udp.endPacket();
}

// ---------- PC 注册握手 ----------

void checkRegistration() {
  int packetSize = udp.parsePacket();

  if (packetSize > 0) {
    while (udp.available()) {
      udp.read();
    }

    IPAddress from = udp.remoteIP();

    if (!hasTarget || from != targetIP) {
      targetIP = from;
      hasTarget = true;

      Serial.print("PC registered: ");
      Serial.println(targetIP);
    }
  }
}

// ============================================================
// MPU 初始化（量程/滤波与 legacy 数据完全一致）
// ============================================================

void initMPU() {
  uint8_t who = readRegister(0x75);

  Serial.print("WHO_AM_I = 0x");
  Serial.println(who, HEX);

  if (who != 0x70) {
    // 身份不对：警告但不挂死，方便排查接线
    Serial.println("WARN: MPU6500 not detected, check wiring!");
  }

  // Reset
  writeRegister(0x6B, 0x80);
  delay(100);

  // Wake up, clock = PLL
  writeRegister(0x6B, 0x01);
  delay(10);

  writeRegister(0x6C, 0x00);

  // 采样率 1kHz / (1 + 9) = 100 Hz
  writeRegister(0x19, 9);

  // Gyro DLPF 44Hz
  writeRegister(0x1A, 0x03);

  // Gyro ±1000 deg/s（32.8 LSB/deg/s）
  writeRegister(0x1B, 0x10);

  // Accel ±8g（4096 LSB/g）
  writeRegister(0x1C, 0x10);

  // Accel DLPF ~44Hz
  writeRegister(0x1D, 0x03);

  delay(10);

  Serial.println("MPU initialized");
}

// ============================================================
// Wi-Fi
// ============================================================

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("Connecting WiFi");

  unsigned long start = millis();

  while (
    WiFi.status() != WL_CONNECTED &&
    millis() - start < 10000
  ) {
    delay(300);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("WiFi connected!");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());

    udp.begin(4211);
  } else {
    Serial.println("WiFi connection failed.");
  }
}

// ============================================================
// Setup
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("=== GestureMusic firmware (stream + beat) ===");

  Wire.begin(SDA_PIN, SCL_PIN);

  initMPU();

  connectWiFi();
}

// ============================================================
// Loop
// ============================================================

void loop() {
  unsigned long now = millis();

  // ---------- PC 注册检查 ----------

  checkRegistration();

  // ---------- Wi-Fi 重连 ----------

  if (
    WiFi.status() != WL_CONNECTED &&
    now - lastWifiCheck > 3000
  ) {
    lastWifiCheck = now;

    Serial.println("WiFi disconnected, reconnecting...");

    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    // 等本轮重连结果
    unsigned long start = millis();

    while (
      WiFi.status() != WL_CONNECTED &&
      millis() - start < 8000
    ) {
      delay(200);
    }

    // 重连成功必须重新打开监听端口，
    // 否则永远收不到PC注册包
    if (WiFi.status() == WL_CONNECTED) {
      udp.begin(4211);

      Serial.println("Reconnected, UDP listening.");
    }
  }

  // ---------- 每秒一条心跳 ----------

  if (now - lastAliveTime > 1000) {
    lastAliveTime = now;

    sendUDP(
      "ALIVE," + String(WiFi.RSSI())
    );
  }

  // ---------- 100Hz 数据流 ----------

  static unsigned long lastSample = 0;

  unsigned long t = micros();

  if (t - lastSample < 10000) {
    return;
  }

  lastSample += 10000;

  uint8_t data[14];

  if (!readRegisters(0x3B, data, 14)) {
    return;
  }

  int16_t rawAx = (data[0] << 8) | data[1];
  int16_t rawAy = (data[2] << 8) | data[3];
  int16_t rawAz = (data[4] << 8) | data[5];

  int16_t rawGx = (data[8] << 8) | data[9];
  int16_t rawGy = (data[10] << 8) | data[11];
  int16_t rawGz = (data[12] << 8) | data[13];

  // 单位：m/s^2 与 rad/s，与 legacy 数据一致
  float ax = rawAx / 4096.0 * 9.80665;
  float ay = rawAy / 4096.0 * 9.80665;
  float az = rawAz / 4096.0 * 9.80665;

  float gx = rawGx / 32.8 * 0.01745329252;
  float gy = rawGy / 32.8 * 0.01745329252;
  float gz = rawGz / 32.8 * 0.01745329252;

  // ---------- 原始数据包 ----------

  char packet[160];

  snprintf(
    packet,
    sizeof(packet),
    "%lu,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f",
    millis(),
    ax, ay, az,
    gx, gy, gz
  );

  sendUDP(packet);

  // ---------- Beat 检测（内部用 deg/s） ----------

  float gyDeg = gy * 57.2957795;

  if (
    beatDirection == 0 &&
    fabs(gyDeg) > CALIBRATION_THRESHOLD
  ) {
    beatDirection = (gyDeg > 0) ? 1 : -1;

    Serial.print("Downstroke direction calibrated: ");
    Serial.println(beatDirection);

    float speed = fabs(gyDeg);

    sendUDP("BEAT," + String(speed, 1));

    lastBeatTime = now;
    beatArmed = false;
  }

  if (beatDirection != 0) {
    float directedSpeed = beatDirection * gyDeg;

    if (
      beatArmed
      && directedSpeed > BEAT_THRESHOLD
      && now - lastBeatTime > COOLDOWN_MS
    ) {
      sendUDP("BEAT," + String(directedSpeed, 1));

      lastBeatTime = now;
      beatArmed = false;
    }

    if (
      !beatArmed
      && fabs(gyDeg) < RESET_THRESHOLD
    ) {
      beatArmed = true;
    }
  }
}
