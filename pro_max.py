import math
import tkinter as tk
import customtkinter as ctk
import RPi.GPIO as GPIO
import serial
import time
import threading


class RetroPhoneApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.geometry("800x800+0+0")
        self.configure(fg_color="#050505")

        # =========================
        # STATES
        # =========================
        self.STATE_IDLE = "IDLE"
        self.STATE_DIALING = "DIALING"
        self.STATE_CALLING = "CALLING"
        self.STATE_INCOMING = "INCOMING"
        self.STATE_OUTGOING = "OUTGOING"

        self.state = self.STATE_IDLE

        self.number = ""
        self.incoming_number = ""
        self.outgoing_number = ""

        self.incoming_call = False
        self.blink = True

        self.call_sent = False

        # =========================
        # HOOK
        # =========================
        self.stable_hook = GPIO.HIGH

        # =========================
        # ROTARY
        # =========================
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
        # GPIO (22/27 swapped)
        # =========================
        self.HOOK_IN = 27
        self.HOOK_OUT = 22

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.HOOK_OUT, GPIO.OUT)
        GPIO.output(self.HOOK_OUT, GPIO.LOW)

        GPIO.setup(self.HOOK_IN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # =========================
        # SIM800L
        # =========================
        self.ser = serial.Serial("/dev/serial0", 9600, timeout=1)
        time.sleep(1)
        print("SIM800L READY")

        self.running = True
        threading.Thread(target=self.read_sim800, daemon=True).start()

        # =========================
        # UI
        # =========================
        self.canvas = tk.Canvas(self, width=800, height=800, bg="#050505", highlightthickness=0)
        self.canvas.pack()

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.draw()

        self.after(50, self.check_hook)
        self.after(500, self.blink_loop)

    # =========================
    # BLINK
    # =========================
    def blink_loop(self):
        self.blink = not self.blink
        self.draw()
        self.after(500, self.blink_loop)

    # =========================
    # SIM800
    # =========================
    def read_sim800(self):
        while self.running:
            line = self.ser.readline().decode(errors="ignore").strip()

            if "RING" in line:
                self.incoming_call = True
                self.state = self.STATE_INCOMING

            if "+CLIP" in line:
                try:
                    self.incoming_number = line.split('"')[1]
                except:
                    pass

            time.sleep(0.1)

    def send_at(self, cmd):
        self.ser.write((cmd + "\r").encode())
        print(">>", cmd)

    # =========================
    # CALLS
    # =========================
    def call_number(self, number):
        if self.call_sent:
            return

        self.outgoing_number = number
        self.state = self.STATE_OUTGOING

        print(f"📞 CALLING: {number}")
        self.send_at("ATD" + number + ";")

        self.call_sent = True

    def answer_call(self):
        self.send_at("ATA")
        self.state = self.STATE_CALLING
        self.incoming_call = False

    def hangup(self):
        self.send_at("ATH")
        self.state = self.STATE_IDLE
        self.call_sent = False
        self.incoming_call = False
        self.incoming_number = ""
        self.outgoing_number = ""

    # =========================
    # HOOK
    # =========================
    def check_hook(self):
        raw = GPIO.input(self.HOOK_IN)

        if raw != self.stable_hook:
            self.stable_hook = raw

            # HOOK OFF
            if raw == GPIO.LOW:
                print("📞 HOOK OFF")

                if self.incoming_call:
                    self.answer_call()
                else:
                    formatted = self.format_number(self.number)
                    if formatted:
                        self.call_number(formatted)

            # HOOK ON
            else:
                print("📴 HOOK ON")
                self.hangup()
                self.number = ""

            self.draw()

        self.after(50, self.check_hook)

    # =========================
    # FORMAT
    # =========================
    def format_number(self, num):
        if len(num) == 11 and num.startswith("8"):
            return num
        if len(num) == 10:
            return "8" + num
        return None

    # =========================
    # DRAW
    # =========================
    def draw(self):
        self.canvas.delete("all")
        cx, cy = 400, 400

        # =========================
        # INCOMING
        # =========================
        if self.state == self.STATE_INCOMING and self.blink:
            self.canvas.create_text(cx, 220, text="⬇", fill="#22c55e", font=("Arial", 120, "bold"))
            self.canvas.create_text(cx, 340, text="ВХОДЯЩИЙ ВЫЗОВ", fill="#22c55e", font=("Arial", 34, "bold"))
            self.canvas.create_text(cx, 420, text=self.incoming_number, fill="#e5e7eb", font=("Arial", 30, "bold"))
            return

        # =========================
        # OUTGOING
        # =========================
        if self.state == self.STATE_OUTGOING and self.blink:
            self.canvas.create_text(cx, 220, text="⬆", fill="#3b82f6", font=("Arial", 120, "bold"))
            self.canvas.create_text(cx, 340, text="ИСХОДЯЩИЙ ВЫЗОВ", fill="#3b82f6", font=("Arial", 34, "bold"))
            self.canvas.create_text(cx, 420, text=self.outgoing_number, fill="#e5e7eb", font=("Arial", 30, "bold"))
            return

        # =========================
        # DIAL UI
        # =========================
        r = 275

        self.canvas.create_oval(5, 5, 795, 795, fill="#020617")
        self.canvas.create_oval(40, 40, 760, 760, fill="#111827")
        self.canvas.create_oval(120, 120, 680, 680, fill="#020617")

        for d in self.digits:
            ang = self.angle_map[d] + self.angle_offset - self.dial_angle
            rad = math.radians(ang)

            x = cx + r * math.cos(rad)
            y = cy - r * math.sin(rad)

            self.canvas.create_oval(x-45, y-45, x+45, y+45,
                                    fill="#f8fafc", outline="#94a3b8", width=2)

            self.canvas.create_text(x, y, text=d,
                                    font=("Arial", 28, "bold"),
                                    fill="#0f172a")

        self.canvas.create_text(cx, cy - 90,
                                text=self.number if self.number else self.state,
                                fill="#e5e7eb",
                                font=("Arial", 26, "bold"))

    # =========================
    # ROTARY (без изменений логики)
    # =========================
    def on_press(self, e):
        self.selected_digit = self.detect_digit(e.x, e.y)
        if not self.selected_digit:
            return

        self.dragging = True
        self.start_angle = self.get_angle(e.x, e.y)
        self.dial_angle = 0

    def on_drag(self, e):
        if not self.dragging:
            return

        cur = self.get_angle(e.x, e.y)
        self.dial_angle = (self.start_angle - cur) % 360
        self.draw()

    def on_release(self, e):
        if not self.dragging:
            return

        if self.dial_angle >= 60:
            self.number += self.selected_digit

        self.dragging = False
        self.selected_digit = None
        self.animate_back()

    def animate_back(self):
        if self.dial_angle <= 0:
            self.dial_angle = 0
            self.draw()
            return

        self.dial_angle -= 18
        self.draw()
        self.after(10, self.animate_back)

    # =========================
    # HELPERS
    # =========================
    def get_angle(self, x, y):
        dx = x - 400
        dy = 400 - y
        return (math.degrees(math.atan2(dy, dx)) + 360) % 360

    def detect_digit(self, x, y):
        cx, cy = 400, 400
        r = 275

        best = None
        bd = 1e9

        for d, ang in self.angle_map.items():
            rad = math.radians(ang + self.angle_offset)

            dx = cx + r * math.cos(rad)
            dy = cy - r * math.sin(rad)

            dist = (dx - x) ** 2 + (dy - y) ** 2

            if dist < bd:
                best = d
                bd = dist

        return best if bd < 70 ** 2 else None


if __name__ == "__main__":
    app = RetroPhoneApp()
    app.mainloop()
