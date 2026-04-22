// ======================================================
// ТЕСТ КАТУШКИ ЗВОНКА ЧЕРЕЗ ДРАЙВЕР
// Пины Arduino:
// IN1 -> D10
// IN2 -> D11
// ======================================================

const int IN1 = 10;
const int IN2 = 11;

// Подбери экспериментально.
// Чем меньше delayMs, тем быстрее переключение.
int delayMs = 40;

// Сколько миллисекунд звонить в одной серии
int ringTime = 2000;

// Пауза между сериями
int pauseTime = 2000;

void setup() {
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);

  // На старте всё выключено
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);

  Serial.begin(9600);
  Serial.println("Тест звонковой катушки запущен");
}

void loop() {
  Serial.println("Серия звонков...");

  unsigned long startTime = millis();

  while (millis() - startTime < ringTime) {
    // Полярность 1
    digitalWrite(IN1, HIGH);
    digitalWrite(IN2, LOW);
    delay(delayMs);

    // Короткая пауза
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
    delay(5);

    // Полярность 2
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, HIGH);
    delay(delayMs);

    // Короткая пауза
    digitalWrite(IN1, LOW);
    digitalWrite(IN2, LOW);
    delay(5);
  }

  // Полностью выключаем катушку
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);

  Serial.println("Пауза...");
  delay(pauseTime);
}
