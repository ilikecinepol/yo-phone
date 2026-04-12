#include <SoftwareSerial.h>

SoftwareSerial sim800(9, 8); // D2=RX, D3=TX

void sendCmd(const char* cmd, unsigned long waitMs = 1500) {
  Serial.print("\n>> ");
  Serial.println(cmd);
  sim800.println(cmd);

  unsigned long t0 = millis();
  while (millis() - t0 < waitMs) {
    while (sim800.available()) {
      Serial.write(sim800.read());
    }
  }
  Serial.println();
}

void setup() {
  Serial.begin(9600);
  sim800.begin(9600);
  delay(5000);

  Serial.println("Start");
  sendCmd("AT");
  sendCmd("AT+CPIN?");
  sendCmd("AT+CSQ");
  sendCmd("AT+CREG?");
}

void loop() {
  while (sim800.available()) {
    Serial.write(sim800.read());
  }

  if (Serial.available()) {
    sim800.write(Serial.read());
  }
}