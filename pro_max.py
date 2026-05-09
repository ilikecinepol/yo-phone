import math
import tkinter as tk
import customtkinter as ctk
import RPi.GPIO as GPIO
import serial
import time
import threading
import subprocess

MAX_URL = "https://web.max.ru"


class RetroPhoneApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.geometry("800x800+0+0")
        self.configure(fg_color="#050505")

        self.STATE_IDLE = "IDLE"
        self.STATE_CALLING = "CALLING"
        self.STATE_INCOMING = "INCOMING"
        self.STATE_OUTGOING = "OUTGOING"
        self.STATE_MENU = "MENU"
        self.STATE_SMS = "SMS"

        self.state = self.STATE_IDLE

        self.number = ""
        self.incoming_number = ""
        self.outgoing_number = ""

        self.incoming_call = False
        self.call_sent = False
        self.answer_sent = False

        self.incoming_call = False
        self.call_sent = False
        self.answer_sent = False
        self.max_opened = False

        self.sms_list = []
        self.sms_selected = None

        self.dragging = False
        self.selected_digit = None
        self.start_angle = 0
        self.dial_angle = 0

        self.angle_offset = 90

        self.angle_map = {
            "2": 0,
            "3": 25,
            "4": 50,
            "5": 75,
            "6": 100,
            "7": 125,
            "8": 150,
            "9": 180,
            "1": 335,
            "0": 205,
        }

        self.digits = list(self.angle_map.keys())

        # =========================
        # GPIO
        # =========================
        self.HOOK_IN = 27
        self.HOOK_OUT = 22

        self.HOOK_OFF_LEVEL = GPIO.LOW

        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.cleanup()
        time.sleep(0.1)

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.HOOK_OUT, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.HOOK_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        self.stable_hook = GPIO.input(self.HOOK_IN)
        print("HOOK START:", "OFF" if self.is_hook_off() else "ON")

        # =========================
        # SIM800L
        # =========================
        self.ser = serial.Serial("/dev/serial0", 9600, timeout=0.1)
        self.serial_lock = threading.Lock()
        self.serial_buffer = ""
        self.waiting_sms_text = False

        time.sleep(1)

        print("SIM800L READY")

        self.send_at("AT")
        time.sleep(0.2)
        self.send_at("ATE0")
        time.sleep(0.2)
        self.send_at("AT+CMEE=2")
        time.sleep(0.2)
        self.send_at("AT+CSCLK=0")
        time.sleep(0.2)
        self.send_at("AT+CLIP=1")
        time.sleep(0.2)
        self.send_at("AT+CMGF=1")
        time.sleep(0.2)
        self.send_at("AT+CNMI=2,2,0,0,0")
        time.sleep(0.2)

        # =========================
        # THREADS
        # =========================
        self.running = True
        threading.Thread(target=self.read_sim800, daemon=True).start()

        # =========================
        # UI
        # =========================
        self.canvas = tk.Canvas(
            self,
            width=800,
            height=800,
            bg="#050505",
            highlightthickness=0
        )
        self.canvas.pack()

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.draw()

        self.after(50, self.check_hook)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # =========================
    # SAFE UI
    # =========================
    def safe_draw(self):
        try:
            self.after(0, self.draw)
        except:
            pass

    # =========================
    # AT
    # =========================
    def send_at(self, cmd):
        try:
            with self.serial_lock:
                self.ser.write((cmd + "\r").encode())
            print(">>", cmd)
        except Exception as e:
            print("AT ERROR:", e)

    # =========================
    # HOOK
    # =========================
    def is_hook_off(self):
        return GPIO.input(self.HOOK_IN) == self.HOOK_OFF_LEVEL

    def check_hook(self):
        try:
            raw = GPIO.input(self.HOOK_IN)

            # =========================
            # СТРАХОВКА: входящий + трубка уже снята
            # ВАЖНО: обновляем stable_hook, иначе следующий цикл
            # может принять это за новое снятие трубки и сбросить UI
            # =========================
            if (self.state == self.STATE_INCOMING or self.incoming_call) and self.is_hook_off():
                print("📞 INCOMING + HOOK OFF -> ANSWER")

                self.stable_hook = raw

                if not self.answer_sent:
                    self.answer_call()

                self.after(50, self.check_hook)
                return

            # =========================
            # ОБРАБОТКА ИЗМЕНЕНИЯ ТРУБКИ
            # =========================
            if raw != self.stable_hook:
                time.sleep(0.05)
                raw2 = GPIO.input(self.HOOK_IN)

                if raw != raw2:
                    self.after(50, self.check_hook)
                    return

                self.stable_hook = raw

                # =========================
                # ТРУБКА СНЯТА
                # =========================
                if self.is_hook_off():
                    print("📞 HOOK OFF")


                    if self.state == self.STATE_INCOMING or self.incoming_call:
                        if not self.answer_sent:
                            self.answer_call()
                    else:
                        n = self.format_number(self.number)

                        if n:
                            self.call_number(n)
                        else:
                            self.draw()

                # =========================
                # ТРУБКА ПОЛОЖЕНА
                # =========================
                else:
                    print("📴 HOOK ON")

                    self.send_at("ATH")

                    self.incoming_call = False
                    self.call_sent = False
                    self.answer_sent = False

                    self.number = ""
                    self.outgoing_number = ""
                    self.incoming_number = ""

                    if self.max_opened:
                        self.close_max()
                        self.after(50, self.check_hook)
                        return
                    self.show_ui()

        except Exception as e:
            print("HOOK ERROR:", e)

        self.after(50, self.check_hook)

    # =========================
    # SIM800 READ
    # =========================
    def read_sim800(self):
        while self.running:
            try:
                data = self.ser.read_all()

                if data:
                    text = data.decode(errors="ignore")
                    self.serial_buffer += text

                    while "\n" in self.serial_buffer:
                        line, self.serial_buffer = self.serial_buffer.split("\n", 1)
                        line = line.replace("\r", "").strip()

                        if line:
                            self.process_sim800_line(line)

            except Exception as e:
                print("SIM800 READ ERROR:", e)

            time.sleep(0.05)

    def process_sim800_line(self, line):
        print("SIM800:", line)

        if self.waiting_sms_text:
            self.waiting_sms_text = False
            self.store_sms(line)
            return

        if line == "RING":
            print("📞 RING DETECTED")

            if self.state != self.STATE_CALLING:
                self.incoming_call = True
                self.answer_sent = False
                self.state = self.STATE_INCOMING

                if self.is_hook_off():
                    print("📞 RING + HOOK ALREADY OFF -> ANSWER")
                    self.after(0, self.answer_call)
                else:
                    self.safe_draw()

            return

        if "+CLIP:" in line:
            try:
                self.incoming_number = line.split('"')[1]
                print("CALLER:", self.incoming_number)
            except:
                self.incoming_number = ""

            self.safe_draw()
            return

        if "+CMT:" in line:
            self.waiting_sms_text = True
            return

        if "NO CARRIER" in line or "BUSY" in line or "NO ANSWER" in line:
            self.incoming_call = False
            self.call_sent = False
            self.answer_sent = False
            self.state = self.STATE_IDLE
            self.safe_draw()
            return

    # =========================
    # SMS
    # =========================
    def decode_sms(self, text):
        try:
            clean = text.replace("\r", "").replace("\n", "").strip()
            if clean and all(c in "0123456789ABCDEFabcdef" for c in clean):
                return bytes.fromhex(clean).decode("utf-16-be")
        except:
            pass

        return text

    def store_sms(self, text):
        decoded = self.decode_sms(text)

        self.sms_list.append(decoded)

        if len(self.sms_list) > 30:
            self.sms_list.pop(0)

        print("📩 SMS STORED:", decoded)
        self.safe_draw()

    # =========================
    # CALLS
    # =========================
    def call_number(self, number):
        if self.call_sent:
            return

        self.outgoing_number = number
        self.state = self.STATE_OUTGOING
        self.call_sent = True

        print("📞 CALLING:", number)
        self.send_at("ATD" + number + ";")

        self.draw()

    def answer_call(self):
        if self.answer_sent:
            return

        print("📞 ANSWER")

        self.answer_sent = True
        self.state = self.STATE_CALLING
        self.incoming_call = False
        self.draw()

        self.after(300, lambda: self.send_at("ATA"))

    def hangup(self):
        print("📴 HANGUP")

        self.send_at("ATH")

        self.state = self.STATE_IDLE
        self.call_sent = False
        self.incoming_call = False
        self.answer_sent = False

        self.number = ""
        self.outgoing_number = ""
        self.incoming_number = ""

        self.draw()

    # =========================
    # NUMBER FORMAT
    # =========================
    def format_number(self, num):
        if len(num) == 11 and num.startswith("8"):
            return num

        if len(num) == 10:
            return "8" + num

        return None

    # =========================
    # MENU
    # =========================
    def open_menu(self):
        self.state = self.STATE_MENU
        self.draw()

    def close_menu(self):
        self.state = self.STATE_IDLE
        self.draw()

    def open_sms(self, index=None):
        if index is not None and (index < 0 or index >= len(self.sms_list)):
            return

        self.sms_selected = index
        self.state = self.STATE_SMS
        self.draw()

    def close_sms(self):
        self.sms_selected = None
        self.state = self.STATE_MENU
        self.draw()

    # =========================
    # MAX
    # =========================
    def open_max(self):
        print("🌐 OPEN MAX")

        self.max_opened = True
        self.withdraw()

        self.max_process = subprocess.Popen([
            "chromium",
            "--kiosk",
            "--noerrdialogs",
            "--disable-session-crashed-bubble",
            "--disable-infobars",
            "--disable-features=TranslateUI",
            "--autoplay-policy=no-user-gesture-required",
            "--use-fake-ui-for-media-stream",
            "--user-data-dir=/home/phone/max_profile",
            "--profile-directory=Default",
            MAX_URL
        ])

    def close_max(self):
        print("⬅ CLOSE MAX")

        self.max_opened = False

        if hasattr(self, "max_process"):
            try:
                self.max_process.terminate()
                self.max_process.wait(timeout=5)
            except:
                try:
                    self.max_process.kill()
                except:
                    pass

        time.sleep(0.5)
        self.show_ui()

        self.show_ui()

    def show_ui(self):
        self.deiconify()

        self.state = self.STATE_IDLE
        self.sms_selected = None
        self.incoming_call = False
        self.call_sent = False

        self.lift()
        self.focus_force()

        self.draw()

    # =========================
    # DRAW
    # =========================
    def draw(self):
        self.canvas.delete("all")

        cx, cy = 400, 400

        if self.state == self.STATE_SMS:
            self.canvas.create_text(
                400,
                80,
                text="SMS",
                fill="white",
                font=("Arial", 30, "bold")
            )

            if self.sms_selected is not None:
                msg = self.sms_list[self.sms_selected]

                self.canvas.create_text(
                    400,
                    280,
                    text=msg,
                    fill="white",
                    width=600,
                    font=("Arial", 20)
                )

                self.canvas.create_rectangle(
                    300,
                    700,
                    500,
                    770,
                    fill="#dc2626",
                    tags="back_sms"
                )

                self.canvas.create_text(
                    400,
                    735,
                    text="Назад",
                    fill="white",
                    font=("Arial", 20, "bold"),
                    tags="back_sms"
                )

                self.canvas.tag_bind(
                    "back_sms",
                    "<Button-1>",
                    lambda e: self.open_sms(None)
                )

                return

            y = 180

            if not self.sms_list:
                self.canvas.create_text(
                    400,
                    360,
                    text="SMS пока нет",
                    fill="gray",
                    font=("Arial", 24)
                )

            for i, msg in enumerate(self.sms_list[-5:]):
                idx = len(self.sms_list) - len(self.sms_list[-5:]) + i

                self.canvas.create_rectangle(
                    120,
                    y - 40,
                    680,
                    y + 40,
                    fill="#1f2937",
                    tags=f"sms_{idx}"
                )

                preview = msg[:30] + ("..." if len(msg) > 30 else "")

                self.canvas.create_text(
                    400,
                    y,
                    text=preview,
                    fill="white",
                    font=("Arial", 16),
                    tags=f"sms_{idx}"
                )

                self.canvas.tag_bind(
                    f"sms_{idx}",
                    "<Button-1>",
                    lambda e, i=idx: self.open_sms(i)
                )

                y += 100

            self.canvas.create_rectangle(
                300,
                700,
                500,
                770,
                fill="#dc2626",
                tags="back_sms"
            )

            self.canvas.create_text(
                400,
                735,
                text="Назад",
                fill="white",
                font=("Arial", 20, "bold"),
                tags="back_sms"
            )

            self.canvas.tag_bind(
                "back_sms",
                "<Button-1>",
                lambda e: self.close_sms()
            )

            return

        if self.state == self.STATE_MENU:
            self.canvas.create_text(
                cx,
                120,
                text="МЕНЮ",
                fill="white",
                font=("Arial", 36, "bold")
            )

            self.canvas.create_rectangle(
                200,
                220,
                600,
                300,
                fill="#1f2937",
                tags="max"
            )

            self.canvas.create_text(
                cx,
                260,
                text="MAX",
                fill="white",
                font=("Arial", 24, "bold"),
                tags="max"
            )

            self.canvas.create_rectangle(
                200,
                340,
                600,
                420,
                fill="#1f2937",
                tags="sms"
            )

            self.canvas.create_text(
                cx,
                380,
                text="SMS",
                fill="white",
                font=("Arial", 24, "bold"),
                tags="sms"
            )

            self.canvas.create_rectangle(
                200,
                580,
                600,
                660,
                fill="#dc2626",
                tags="menu_back"
            )

            self.canvas.create_text(
                cx,
                620,
                text="НАЗАД",
                fill="white",
                font=("Arial", 24, "bold"),
                tags="menu_back"
            )

            self.canvas.tag_bind("max", "<Button-1>", lambda e: self.open_max())
            self.canvas.tag_bind("sms", "<Button-1>", lambda e: self.open_sms(None))
            self.canvas.tag_bind("menu_back", "<Button-1>", lambda e: self.close_menu())

            return

        if self.state == self.STATE_INCOMING:
            self.canvas.create_text(
                400,
                120,
                text="ВХОДЯЩИЙ ЗВОНОК",
                fill="white",
                font=("Arial", 30, "bold")
            )

            self.canvas.create_text(
                400,
                200,
                text=self.incoming_number or "Неизвестный номер",
                fill="#22c55e",
                font=("Arial", 26, "bold")
            )

            self.canvas.create_text(
                400,
                320,
                text="⬇",
                fill="#22c55e",
                font=("Arial", 80, "bold")
            )

            self.canvas.create_text(
                400,
                500,
                text="Снимите трубку",
                fill="gray",
                font=("Arial", 18)
            )

            return

        if self.state == self.STATE_OUTGOING:
            self.canvas.create_text(
                400,
                120,
                text="ИСХОДЯЩИЙ ЗВОНОК",
                fill="white",
                font=("Arial", 30, "bold")
            )

            self.canvas.create_text(
                400,
                200,
                text=self.outgoing_number,
                fill="#60a5fa",
                font=("Arial", 26, "bold")
            )

            self.canvas.create_text(
                400,
                320,
                text="📞",
                fill="#60a5fa",
                font=("Arial", 80, "bold")
            )

            self.canvas.create_text(
                400,
                500,
                text="Идёт набор...",
                fill="gray",
                font=("Arial", 18)
            )

            return

        if self.state == self.STATE_CALLING:
            self.canvas.create_text(
                400,
                120,
                text="РАЗГОВОР",
                fill="white",
                font=("Arial", 30, "bold")
            )

            self.canvas.create_text(
                400,
                200,
                text=self.incoming_number or self.outgoing_number,
                fill="#fbbf24",
                font=("Arial", 26, "bold")
            )

            self.canvas.create_text(
                400,
                320,
                text="● ● ●",
                fill="#fbbf24",
                font=("Arial", 50, "bold")
            )

            self.canvas.create_text(
                400,
                520,
                text="Положите трубку для завершения",
                fill="gray",
                font=("Arial", 18)
            )

            return

        # MAIN DIAL
        self.canvas.create_oval(5, 5, 795, 795, fill="#020617")
        self.canvas.create_oval(40, 40, 760, 760, fill="#111827")

        for d in self.digits:
            ang = self.angle_map[d] + self.angle_offset - self.dial_angle
            rad = math.radians(ang)

            x = cx + 275 * math.cos(rad)
            y = cy - 275 * math.sin(rad)

            self.canvas.create_oval(
                x - 45,
                y - 45,
                x + 45,
                y + 45,
                fill="white"
            )

            self.canvas.create_text(
                x,
                y,
                text=d,
                font=("Arial", 24, "bold")
            )

        self.canvas.create_text(
            cx,
            cy - 90,
            text=self.number or "Номер",
            fill="white",
            font=("Arial", 48, "bold")
        )

        self.canvas.create_oval(
            350,
            350,
            450,
            450,
            fill="#1e293b",
            tags="menu"
        )

        self.canvas.create_text(
            cx,
            cy,
            text="☰",
            fill="white",
            font=("Arial", 32, "bold"),
            tags="menu"
        )

        self.canvas.tag_bind("menu", "<Button-1>", lambda e: self.open_menu())

    # =========================
    # ROTARY
    # =========================
    def on_press(self, e):
        if self.state != self.STATE_IDLE:
            return

        self.selected_digit = self.detect_digit(e.x, e.y)

        if not self.selected_digit:
            return

        self.dragging = True
        self.start_angle = self.get_angle(e.x, e.y)
        self.dial_angle = 0

    def on_drag(self, e):
        if not self.dragging:
            return

        self.dial_angle = (self.start_angle - self.get_angle(e.x, e.y)) % 360
        self.draw()

    def on_release(self, e):
        if not self.dragging:
            return

        if self.dial_angle >= 60:
            self.number += self.selected_digit

        self.dragging = False
        self.animate_back()

    def animate_back(self):
        if self.dial_angle <= 0:
            self.dial_angle = 0
            self.draw()
            return

        self.dial_angle -= 18

        if self.dial_angle < 0:
            self.dial_angle = 0

        self.draw()
        self.after(10, self.animate_back)

    def get_angle(self, x, y):
        return (math.degrees(math.atan2(400 - y, x - 400)) + 360) % 360

    def detect_digit(self, x, y):
        best = None
        bd = 1e9

        for d, a in self.angle_map.items():
            rad = math.radians(a + self.angle_offset)

            dx = 400 + 275 * math.cos(rad)
            dy = 400 - 275 * math.sin(rad)

            dist = (dx - x) ** 2 + (dy - y) ** 2

            if dist < bd:
                best = d
                bd = dist

        return best if bd < 4900 else None

    # =========================
    # CLOSE
    # =========================
    def on_close(self):
        self.running = False

        try:
            self.send_at("ATH")
        except:
            pass

        try:
            if hasattr(self, "max_process"):
                self.max_process.terminate()
        except:
            pass

        try:
            self.ser.close()
        except:
            pass

        try:
            GPIO.cleanup()
        except:
            pass

        self.destroy()


if __name__ == "__main__":
    app = RetroPhoneApp()
    app.mainloop()
