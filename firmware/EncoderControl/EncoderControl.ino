/*
  Desktop rotary-encoder controller for GestureMusic.

  Wiring (ESP32-S3): module 5V -> 3V3, GND -> GND,
  S1 -> GPIO4, S2 -> GPIO5, KEY -> GPIO6.

  USB serial output, 115200 baud:
    {"type":"encoder","delta":1}
    {"type":"encoder","delta":-1}
    {"type":"encoder","press":"short"}
    {"type":"encoder","press":"long"}
*/

constexpr uint8_t PIN_S1 = 4;
constexpr uint8_t PIN_S2 = 5;
constexpr uint8_t PIN_KEY = 6;

constexpr unsigned long BUTTON_DEBOUNCE_MS = 25;
constexpr unsigned long LONG_PRESS_MS = 800;
constexpr int COUNTS_PER_STEP = 4;  // Standard EC11: four valid edges per detent.

uint8_t previousAB;
int encoderCounts = 0;

bool rawPressed = false;
bool stablePressed = false;
unsigned long lastButtonChange = 0;
unsigned long pressStartedAt = 0;


uint8_t readAB() {
  return (digitalRead(PIN_S1) << 1) | digitalRead(PIN_S2);
}


void emitTurn(int delta) {
  Serial.print("{\"type\":\"encoder\",\"delta\":");
  Serial.print(delta);
  Serial.println("}");
}


void emitPress(const char* kind) {
  Serial.print("{\"type\":\"encoder\",\"press\":\"");
  Serial.print(kind);
  Serial.println("\"}");
}


void readEncoder() {
  // Invalid transitions caused by contact bounce produce zero, rather than a turn.
  static const int8_t transition[16] = {
       0, -1,  1,  0,
       1,  0,  0, -1,
      -1,  0,  0,  1,
       0,  1, -1,  0,
  };

  uint8_t currentAB = readAB();
  encoderCounts += transition[(previousAB << 2) | currentAB];
  previousAB = currentAB;

  if (encoderCounts >= COUNTS_PER_STEP) {
    emitTurn(1);
    encoderCounts = 0;
  } else if (encoderCounts <= -COUNTS_PER_STEP) {
    emitTurn(-1);
    encoderCounts = 0;
  }
}


void readButton(unsigned long now) {
  bool pressed = digitalRead(PIN_KEY) == LOW;
  if (pressed != rawPressed) {
    rawPressed = pressed;
    lastButtonChange = now;
  }

  if (pressed == stablePressed || now - lastButtonChange < BUTTON_DEBOUNCE_MS) {
    return;
  }

  stablePressed = pressed;
  if (stablePressed) {
    pressStartedAt = now;
  } else {
    emitPress(now - pressStartedAt >= LONG_PRESS_MS ? "long" : "short");
  }
}


void setup() {
  Serial.begin(115200);
  pinMode(PIN_S1, INPUT_PULLUP);
  pinMode(PIN_S2, INPUT_PULLUP);
  pinMode(PIN_KEY, INPUT_PULLUP);

  previousAB = readAB();
  delay(50);
  Serial.println("{\"type\":\"encoder\",\"status\":\"ready\"}");
}


void loop() {
  readEncoder();
  readButton(millis());
  delay(1);
}
