// =====================================================
// Arduino Leonardo / Pro Micro + SIM800L
//
// SIM800L:
// D1 TX1 -> делитель -> RX SIM800L
// D0 RX1 <- TX SIM800L
//
// Дисковый номеронабиратель:
// D2 -> PULSE
// D3 -> GATE
//
// Кнопки:
// D4 -> красная кнопка -> GND
// D5 -> зеленая кнопка -> GND
// =====================================================

#define sim800 Serial1

const uint8_t PIN_PULSE = 2;
const uint8_t PIN_GATE  = 3;

const uint8_t BTN_RED   = 4;
const uint8_t BTN_GREEN = 5;

const uint8_t PIEZO_PIN = 6;

const unsigned long DEBOUNCE_US = 4000UL;
const unsigned long BUTTON_DEBOUNCE_MS = 80;
const unsigned long DIAL_TIMEOUT = 3000;

volatile bool counting = false;
volatile uint16_t pulses = 0;

volatile uint8_t lastPulse = 1;
volatile uint8_t lastGate  = 1;

volatile unsigned long lastPulseChangeUs = 0;
volatile unsigned long lastGateChangeUs = 0;

volatile bool digitReady = false;
volatile uint8_t digitValue = 0;

String phoneNumber = "";
unsigned long lastDigitTime = 0;

bool incomingCall = false;
bool callActive = false;

String simLine = "";

// =====================================================
// SIM800
// =====================================================

void sendAT(const String &cmd) {
  sim800.println(cmd);
  Serial.print(">> ");
  Serial.println(cmd);
}

void answerCall() {
  Serial.println("Answering call...");
  noTone(PIEZO_PIN);
  sendAT("ATA");

  incomingCall = false;
  callActive = true;
}

void hangUpCall() {
  Serial.println("Hanging up...");
  noTone(PIEZO_PIN);
  sendAT("ATH");

  incomingCall = false;
  callActive = false;
  phoneNumber = "";
}

void processSim800Line(String line) {
  line.trim();
  if (line.length() == 0) return;

  Serial.print("SIM800: ");
  Serial.println(line);

  if (line == "RING") {
    Serial.println("INCOMING CALL");
    incomingCall = true;
    callActive = false;
    tone(PIEZO_PIN, 2000);
  }
  else if (line == "NO CARRIER" || line == "BUSY" || line == "NO ANSWER") {
    incomingCall = false;
    callActive = false;
    phoneNumber = "";
    noTone(PIEZO_PIN);
  }
  else if (line == "ERROR") {
    callActive = false;
  }
}

void readSim800() {
  while (sim800.available()) {
    char c = sim800.read();

    if (c == '\n') {
      processSim800Line(simLine);
      simLine = "";
    } else if (c != '\r') {
      simLine += c;
    }
  }
}

// =====================================================
// Номер
// =====================================================

String normalizeNumber(String num) {
  num.trim();

  if (num.length() == 11 && num[0] == '8') return "+7" + num.substring(1);
  if (num.length() == 11 && num[0] == '7') return "+7" + num.substring(1);
  if (num.length() == 10) return "+7" + num;

  return num;
}

void makeCall(String rawNumber) {
  String finalNumber = normalizeNumber(rawNumber);

  if (finalNumber.length() == 0) {
    Serial.println("Empty number");
    return;
  }

  Serial.print("Calling: ");
  Serial.println(finalNumber);

  sim800.print("ATD");
  sim800.print(finalNumber);
  sim800.println(";");

  callActive = true;
}

void handleDigit() {
  if (!digitReady) return;

  noInterrupts();
  uint8_t d = digitValue;
  digitReady = false;
  interrupts();

  Serial.print("Digit: ");
  Serial.println(d);

  phoneNumber += String(d);
  lastDigitTime = millis();

  Serial.print("Number: ");
  Serial.println(phoneNumber);
}

// =====================================================
// Кнопки
// =====================================================

void handleButtons() {
  static bool lastRed = HIGH;
  static bool lastGreen = HIGH;

  static unsigned long lastRedMs = 0;
  static unsigned long lastGreenMs = 0;

  bool redNow = digitalRead(BTN_RED);
  bool greenNow = digitalRead(BTN_GREEN);

  unsigned long now = millis();

  if (lastRed == HIGH && redNow == LOW && now - lastRedMs > BUTTON_DEBOUNCE_MS) {
    lastRedMs = now;

    Serial.println("RED BUTTON");
    hangUpCall();
  }

  if (lastGreen == HIGH && greenNow == LOW && now - lastGreenMs > BUTTON_DEBOUNCE_MS) {
    lastGreenMs = now;

    Serial.println("GREEN BUTTON");

    if (incomingCall) {
      answerCall();
    } else if (phoneNumber.length() > 0) {
      makeCall(phoneNumber);
      phoneNumber = "";
    } else {
      Serial.println("No incoming call and no number");
    }
  }

  lastRed = redNow;
  lastGreen = greenNow;
}

// =====================================================
// Дисковый номеронабиратель — рабочая логика из теста
// =====================================================

void gateISR() {
  unsigned long nowUs = micros();

  uint8_t gate = digitalRead(PIN_GATE);

  if (gate != lastGate) {
    if (nowUs - lastGateChangeUs >= DEBOUNCE_US) {

      // старт окна: HIGH -> LOW
      if (lastGate == HIGH && gate == LOW) {
        counting = true;
        pulses = 0;
      }

      // стоп окна: LOW -> HIGH
      else if (lastGate == LOW && gate == HIGH) {
        if (counting) {
          counting = false;

          uint8_t n = (pulses % 10 == 0) ? 0 : (pulses % 10);

          digitValue = n;
          digitReady = true;
          pulses = 0;
        }
      }

      lastGate = gate;
      lastGateChangeUs = nowUs;
    }
  }
}

void pulseISR() {
  unsigned long nowUs = micros();

  uint8_t pulse = digitalRead(PIN_PULSE);
  uint8_t gate  = digitalRead(PIN_GATE);

  if (pulse != lastPulse) {
    if (nowUs - lastPulseChangeUs >= DEBOUNCE_US) {

      if (!counting && gate == LOW) {
        counting = true;
        pulses = 0;
      }

      // считаем LOW -> HIGH только в окне
      if (counting && lastPulse == LOW && pulse == HIGH) {
        pulses++;
      }

      lastPulse = pulse;
      lastPulseChangeUs = nowUs;
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  Serial.begin(9600);

  unsigned long serialStart = millis();
  while (!Serial && millis() - serialStart < 3000) {}

  sim800.begin(9600);

  pinMode(PIN_PULSE, INPUT_PULLUP);
  pinMode(PIN_GATE, INPUT_PULLUP);

  pinMode(BTN_RED, INPUT_PULLUP);
  pinMode(BTN_GREEN, INPUT_PULLUP);

  pinMode(PIEZO_PIN, OUTPUT);
  noTone(PIEZO_PIN);

  lastPulse = digitalRead(PIN_PULSE);
  lastGate  = digitalRead(PIN_GATE);

  unsigned long nowUs = micros();
  lastPulseChangeUs = nowUs;
  lastGateChangeUs = nowUs;

  attachInterrupt(digitalPinToInterrupt(PIN_PULSE), pulseISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_GATE), gateISR, CHANGE);

  Serial.println();
  Serial.println("Phone ready: Leonardo / Pro Micro");
  Serial.println("D2 = PULSE, D3 = GATE, D4 = RED, D5 = GREEN");

  delay(1000);

  sendAT("AT");
  delay(300);

  sendAT("ATE0");
  delay(300);

  sendAT("AT+CLIP=1");
  delay(300);

  Serial.println("READY");
}

// =====================================================
// LOOP
// =====================================================

void loop() {
  readSim800();
  handleButtons();
  handleDigit();


  // Ручная отправка AT-команд из Serial Monitor
  while (Serial.available()) {
    sim800.write(Serial.read());
  }
}
