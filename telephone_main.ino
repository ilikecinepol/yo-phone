#include <AltSoftSerial.h>

// --- SIM800 ---
AltSoftSerial sim800; // RX=D8, TX=D9

// --- Rotary dial ---
const uint8_t PIN_PULSE = 5;  // D5
const uint8_t PIN_GATE  = 6;  // D6

const unsigned long DEBOUNCE_US = 4000UL;

volatile bool     counting   = false;
volatile uint16_t pulses     = 0;

volatile uint8_t  lastD5 = 1;
volatile uint8_t  lastD6 = 1;

volatile unsigned long lastD5ChangeUs = 0;
volatile unsigned long lastD6ChangeUs = 0;

volatile bool     digitReady = false;
volatile uint8_t  digitValue = 0;

// --- Номер ---
String phoneNumber = "";
unsigned long lastDigitTime = 0;
const unsigned long DIAL_TIMEOUT = 3000; // пауза после последней цифры

void setup() {
  Serial.begin(9600);
  sim800.begin(9600);

  pinMode(PIN_PULSE, INPUT_PULLUP);
  pinMode(PIN_GATE,  INPUT_PULLUP);

  lastD5 = (PIND >> PIND5) & 0x01;
  lastD6 = (PIND >> PIND6) & 0x01;

  unsigned long nowUs = micros();
  lastD5ChangeUs = nowUs;
  lastD6ChangeUs = nowUs;

  // PCINT для D5 и D6
  PCICR  |= _BV(PCIE2);
  PCMSK2 |= _BV(PCINT21) | _BV(PCINT22);

  sei();

  Serial.println("Phone ready");
}

// Преобразование "как в старом телефоне":
// 8XXXXXXXXXX -> +7XXXXXXXXXX
// 7XXXXXXXXXX -> +7XXXXXXXXXX
// 10 цифр      -> +7XXXXXXXXXX
String normalizeNumber(String num) {
  num.trim();

  if (num.length() == 11 && num[0] == '8') {
    return "+7" + num.substring(1);
  }

  if (num.length() == 11 && num[0] == '7') {
    return "+7" + num.substring(1);
  }

  if (num.length() == 10) {
    return "+7" + num;
  }

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

  // ---- D6 (окно) ----
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

  // ---- D5 (импульсы) ----
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
  while (sim800.available()) {
    Serial.write(sim800.read());
  }

  if (digitReady) {
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

  // После паузы звоним
  if (phoneNumber.length() > 0 &&
      millis() - lastDigitTime > DIAL_TIMEOUT) {
    makeCall(phoneNumber);
    phoneNumber = "";
  }

  // Ручной ввод AT-команд из Serial Monitor
  while (Serial.available()) {
    sim800.write(Serial.read());
  }
}