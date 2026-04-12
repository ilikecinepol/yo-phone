/* Rotary dial (UNO, PCINT) с подавлением дребезга
 * D5: LOW@idle, считаем LOW->HIGH (размыкания)
 * D6: LOW@idle, окно активно пока D6=LOW, стоп на D6 LOW->HIGH
 * 10 импульсов = 0
 */

const uint8_t PIN_PULSE = 5;  // D5
const uint8_t PIN_GATE  = 6;  // D6

// Порог подавления дребезга контактов (микросекунды)
// 2000–5000 обычно достаточно; при сильном дребезге увеличьте.
const unsigned long DEBOUNCE_US = 4000UL;

volatile bool     counting   = false;
volatile uint16_t pulses     = 0;

volatile uint8_t  lastD5 = 1;          // 1=HIGH, 0=LOW
volatile uint8_t  lastD6 = 1;

volatile unsigned long lastD5ChangeUs = 0;
volatile unsigned long lastD6ChangeUs = 0;

volatile bool     digitReady = false;
volatile uint8_t  digitValue = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_PULSE, INPUT_PULLUP);
  pinMode(PIN_GATE,  INPUT_PULLUP);

  // стартовые уровни
  lastD5 = (PIND >> PIND5) & 0x01;  // ожидаем LOW в покое
  lastD6 = (PIND >> PIND6) & 0x01;  // ожидаем LOW в покое
  unsigned long nowUs = micros();
  lastD5ChangeUs = nowUs;
  lastD6ChangeUs = nowUs;

  // Включаем PCINT для PORTD (D0..D7)
  PCICR  |= _BV(PCIE2);
  PCMSK2 |= _BV(PCINT21) | _BV(PCINT22); // D5, D6

  sei();
  Serial.println(F("Rotary dial ready (debounced)."));
}

ISR(PCINT2_vect) {
  uint8_t pind = PIND;
  unsigned long nowUs = micros();

  // ---- D6 (окно) ----
  uint8_t d6 = (pind >> PIND6) & 0x01;
  if (d6 != lastD6) {
    if (nowUs - lastD6ChangeUs >= DEBOUNCE_US) {
      // старт окна? (редко нужен, т.к. D6 уже LOW в покое, но оставим на случай HIGH->LOW)
      if (lastD6 == 1 && d6 == 0) {      // HIGH->LOW
        counting = true;
        pulses = 0;
      }
      // стоп окна: LOW->HIGH
      else if (lastD6 == 0 && d6 == 1) { // LOW->HIGH
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
      // если пошёл импульс на D5 и «окно» формально не открыто,
      // но D6 сейчас LOW (покой), разрешим старт, чтобы не потерять первую цифру
      if (!counting && (((pind >> PIND6) & 0x01) == 0)) {
        counting = true;
        pulses = 0;
      }

      // считаем только LOW->HIGH (размыкания), и только в окне
      if (counting && lastD5 == 0 && d5 == 1) {
        pulses++;
      }
      lastD5 = d5;
      lastD5ChangeUs = nowUs;
    }
  }
}

void loop() {
  if (digitReady) {
    noInterrupts();
    uint8_t d = digitValue;
    digitReady = false;
    interrupts();

    Serial.println(d); // выводим только цифру
  }
}