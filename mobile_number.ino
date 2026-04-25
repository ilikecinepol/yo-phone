/*
 * Rotary dial test для Arduino Leonardo / Pro Micro
 *
 * D2: PULSE
 *     LOW в покое, считаем LOW -> HIGH
 *
 * D3: GATE
 *     LOW в покое / в окне набора,
 *     стоп цифры на LOW -> HIGH
 *
 * 10 импульсов = 0
 */

const uint8_t PIN_PULSE = 2;
const uint8_t PIN_GATE  = 3;

const unsigned long DEBOUNCE_US = 4000UL;

volatile bool counting = false;
volatile uint16_t pulses = 0;

volatile uint8_t lastPulse = 1;
volatile uint8_t lastGate  = 1;

volatile unsigned long lastPulseChangeUs = 0;
volatile unsigned long lastGateChangeUs = 0;

volatile bool digitReady = false;
volatile uint8_t digitValue = 0;

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

      // если пошёл импульс, а окно ещё не открыто,
      // но gate сейчас LOW — начинаем считать
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

void setup() {
  Serial.begin(115200);

  unsigned long t = millis();
  while (!Serial && millis() - t < 3000) {}

  pinMode(PIN_PULSE, INPUT_PULLUP);
  pinMode(PIN_GATE, INPUT_PULLUP);

  lastPulse = digitalRead(PIN_PULSE);
  lastGate  = digitalRead(PIN_GATE);

  unsigned long nowUs = micros();
  lastPulseChangeUs = nowUs;
  lastGateChangeUs = nowUs;

  attachInterrupt(digitalPinToInterrupt(PIN_PULSE), pulseISR, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_GATE), gateISR, CHANGE);

  Serial.println("Rotary dial ready for Leonardo / Pro Micro");
}

void loop() {
  if (digitReady) {
    noInterrupts();
    uint8_t d = digitValue;
    digitReady = false;
    interrupts();

    Serial.println(d);
  }
}
