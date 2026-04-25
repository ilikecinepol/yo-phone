#include <AltSoftSerial.h>

AltSoftSerial sim800; // RX=D8, TX=D9

const uint8_t PIN_PULSE = 5;
const uint8_t PIN_GATE  = 6;

const uint8_t PIN_HOOK_DOWN = 7; // D7 -> GND, трубка положена
const uint8_t PIN_HOOK_UP   = 4; // D4 -> GND, трубка поднята

const int IN1 = 10;
const int IN2 = 11;

int delayMs = 40;
int ringTime = 2000;
int pauseTime = 2000;

unsigned long lastRingMs = 0;
const unsigned long RING_TIMEOUT_MS = 7000;

const unsigned long DEBOUNCE_US = 4000UL;
const unsigned long HOOK_DEBOUNCE_MS = 120;

volatile bool counting = false;
volatile uint16_t pulses = 0;

volatile uint8_t lastD5 = 1;
volatile uint8_t lastD6 = 1;

volatile unsigned long lastD5ChangeUs = 0;
volatile unsigned long lastD6ChangeUs = 0;

volatile bool digitReady = false;
volatile uint8_t digitValue = 0;

String phoneNumber = "";
unsigned long lastDigitTime = 0;
const unsigned long DIAL_TIMEOUT = 3000;

bool handsetDown = true;
bool lastHandsetDown = true;
unsigned long lastHookChangeMs = 0;

bool incomingCall = false;
bool callActive = false;

String simLine = "";

void setup() {
  Serial.begin(9600);
  sim800.begin(9600);

  pinMode(PIN_PULSE, INPUT_PULLUP);
  pinMode(PIN_GATE, INPUT_PULLUP);
  pinMode(PIN_HOOK_DOWN, INPUT_PULLUP);
  pinMode(PIN_HOOK_UP, INPUT_PULLUP);

  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  stopBell();

  lastD5 = (PIND >> PIND5) & 0x01;
  lastD6 = (PIND >> PIND6) & 0x01;

  unsigned long nowUs = micros();
  lastD5ChangeUs = nowUs;
  lastD6ChangeUs = nowUs;

  handsetDown = readHandsetDown();
  lastHandsetDown = handsetDown;

  PCICR  |= _BV(PCIE2);
  PCMSK2 |= _BV(PCINT21) | _BV(PCINT22);

  sei();

  Serial.println("Phone ready");

  delay(1000);
  sendAT("AT");
  delay(300);
  sendAT("ATE0");
  delay(300);
  sendAT("AT+CLIP=1");
}

void sendAT(const String &cmd) {
  sim800.println(cmd);
  Serial.print(">> ");
  Serial.println(cmd);
}

// D7 имеет приоритет.
// Если D7 замкнут — трубка точно положена.
bool readHandsetDown() {
  bool downContact = (digitalRead(PIN_HOOK_DOWN) == LOW);
  bool upContact   = (digitalRead(PIN_HOOK_UP) == LOW);

  if (downContact) return true;
  if (upContact) return false;

  return handsetDown;
}

void handleHook() {
  bool rawState = readHandsetDown();

  if (rawState != lastHandsetDown) {
    lastHookChangeMs = millis();
    lastHandsetDown = rawState;
  }

  if (millis() - lastHookChangeMs >= HOOK_DEBOUNCE_MS) {
    if (handsetDown != rawState) {
      handsetDown = rawState;

      if (handsetDown) {
        Serial.println("Handset: DOWN");

        hangUpCall();

        incomingCall = false;
        callActive = false;
        phoneNumber = "";
        stopBell();
      } else {
        Serial.println("Handset: UP");

        if (incomingCall) {
          answerCall();
          callActive = true;
          incomingCall = false;
          stopBell();
        }
      }
    }
  }
}

void stopBell() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
}

void updateBell() {
  if (incomingCall && millis() - lastRingMs > RING_TIMEOUT_MS) {
    Serial.println("RING timeout");
    incomingCall = false;
    stopBell();
    return;
  }

  if (!incomingCall || !handsetDown) {
    stopBell();
    return;
  }

  Serial.println("BELL SERIES");

  unsigned long startTime = millis();

  while (millis() - startTime < ringTime) {
    readSim800();
    handleHook();

    if (!incomingCall || !handsetDown) {
      stopBell();
      return;
    }

    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
    delay(delayMs);

    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
    delay(5);

    readSim800();
    handleHook();

    if (!incomingCall || !handsetDown) {
      stopBell();
      return;
    }

    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
    delay(delayMs);

    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
    delay(5);
  }

  stopBell();

  unsigned long pauseStart = millis();

  while (millis() - pauseStart < pauseTime) {
    readSim800();
    handleHook();

    if (!incomingCall || !handsetDown) {
      stopBell();
      return;
    }
  }
}

void answerCall() {
  Serial.println("Answering call...");
  stopBell();
  sim800.println("ATA");
}

void hangUpCall() {
  Serial.println("Hanging up...");
  stopBell();
  sim800.println("ATH");
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
    lastRingMs = millis();
  }
  else if (line.startsWith("+CLIP:")) {
  }
  else if (line == "NO CARRIER" || line == "BUSY" || line == "NO ANSWER") {
    incomingCall = false;
    callActive = false;
    phoneNumber = "";
    stopBell();
  }
  else if (line == "ERROR") {
    callActive = false;
  }
}

void readSim800() {
  while (sim800.available()) {
    char c = sim800.read();
    Serial.write(c);

    if (c == '\n') {
      processSim800Line(simLine);
      simLine = "";
    } else if (c != '\r') {
      simLine += c;
    }
  }
}

String normalizeNumber(String num) {
  num.trim();

  if (num.length() == 11 && num[0] == '8') return "+7" + num.substring(1);
  if (num.length() == 11 && num[0] == '7') return "+7" + num.substring(1);
  if (num.length() == 10) return "+7" + num;

  return "";
}

void makeCall(String rawNumber) {
  String finalNumber = normalizeNumber(rawNumber);

  if (finalNumber == "") {
    Serial.print("Invalid number: ");
    Serial.println(rawNumber);
    return;
  }

  Serial.print("Calling: ");
  Serial.println(finalNumber);

  sim800.print("ATD");
  sim800.print(finalNumber);
  sim800.println(";");

  delay(500);
}

ISR(PCINT2_vect) {
  uint8_t pind = PIND;
  unsigned long nowUs = micros();

  uint8_t d6 = (pind >> PIND6) & 0x01;
  if (d6 != lastD6) {
    if (nowUs - lastD6ChangeUs >= DEBOUNCE_US) {
      if (lastD6 == 1 && d6 == 0) {
        counting = true;
        pulses = 0;
      }
      else if (lastD6 == 0 && d6 == 1) {
        if (counting) {
          counting = false;
          uint8_t n = (pulses % 10 == 0) ? 0 : (pulses % 10);
          digitValue = n;
          digitReady = true;
          pulses = 0;
        }
      }

      lastD6 = d6;
      lastD6ChangeUs = nowUs;
    }
  }

  uint8_t d5 = (pind >> PIND5) & 0x01;
  if (d5 != lastD5) {
    if (nowUs - lastD5ChangeUs >= DEBOUNCE_US) {
      if (!counting && (((pind >> PIND6) & 0x01) == 0)) {
        counting = true;
        pulses = 0;
      }

      if (counting && lastD5 == 0 && d5 == 1) {
        pulses++;
      }

      lastD5 = d5;
      lastD5ChangeUs = nowUs;
    }
  }
}

void loop() {
  readSim800();
  handleHook();
  updateBell();

  if (digitReady) {
    noInterrupts();
    uint8_t d = digitValue;
    digitReady = false;
    interrupts();

    if (!handsetDown) {
      Serial.print("Digit: ");
      Serial.println(d);

      phoneNumber += String(d);
      lastDigitTime = millis();

      Serial.print("Number: ");
      Serial.println(phoneNumber);
    }
  }

  if (!handsetDown &&
      phoneNumber.length() > 0 &&
      millis() - lastDigitTime > DIAL_TIMEOUT) {
    makeCall(phoneNumber);
    phoneNumber = "";
    callActive = true;
  }

  while (Serial.available()) {
    sim800.write(Serial.read());
  }
}
