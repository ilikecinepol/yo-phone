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

        # =========================
        # STATES
        # =========================
        self.STATE_IDLE = "IDLE"
        self.STATE_CALLING = "CALLING"
        self.STATE_INCOMING = "INCOMING"
        self.STATE_OUTGOING = "OUTGOING"
        self.STATE_MENU = "MENU"
        self.STATE_SMS = "SMS"

        self.state = self.STATE_IDLE

        # =========================
        # DATA
        # =========================
        self.number = ""
        self.incoming_number = ""
        self.outgoing_number = ""

        self.incoming_call = False
        self.call_sent = False

        self.signal_level = 0
        self.blink = True

        # SMS STORAGE 📩
        self.sms_list = []

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
            "2": 0, "3": 25, "4": 50, "5": 75,
            "6": 100, "7": 125, "8": 150, "9": 180,
            "1": 335, "0": 205,
        }

        self.digits = list(self.angle_map.keys())

        # =========================
        # GPIO
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

        self.send_at("AT")
        self.send_at("ATE0")
        self.send_at("AT+CLIP=1")

        # SMS MODE 📩
        self.send_at("AT+CMGF=1")
        self.send_at("AT+CNMI=2,2,0,0,0")

        # =========================
        # THREADS
        # =========================
        self.running = True
        threading.Thread(target=self.read_sim800, daemon=True).start()
        threading.Thread(target=self.update_signal_loop, daemon=True).start()

        # =========================
        # UI
        # =========================
        self.canvas = tk.Canvas(self, width=800, height=800,
                                bg="#050505", highlightthickness=0)
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
    # AT
    # =========================
    def send_at(self, cmd):
        self.ser.write((cmd + "\r").encode())
        print(">>", cmd)

    # =========================
    # SMS PARSE 📩
    # =========================
    def handle_sms(self, raw):
        try:
            text = raw.encode().decode("utf-16", errors="ignore")
        except:
            text = raw

        self.sms_list.append(text)

        if len(self.sms_list) > 10:
            self.sms_list.pop(0)

        print("📩 SMS STORED:", text)

    # =========================
    # SIM800 READ
    # =========================
    def decode_ucs2(self, data):
        try:
            bytes_data = bytes.fromhex(data)
            return bytes_data.decode("utf-16-be")
        except:
            return data
    def read_sim800(self):
        while self.running:
            try:
                line = self.ser.readline().decode(errors="ignore").strip()
                if not line:
                    continue

                print("SIM800:", line)

                if "RING" in line:
                    self.incoming_call = True
                    self.state = self.STATE_INCOMING
                    self.draw()

                if "+CLIP" in line:
                    try:
                        self.incoming_number = line.split('"')[1]
                    except:
                        pass

                if "+CMT:" in line:
                    msg = self.ser.readline().decode(errors="ignore").strip()

                    decoded = self.decode_ucs2(msg)

                    self.sms_list.append(decoded)

                    if len(self.sms_list) > 10:
                        self.sms_list.pop(0)

                    print("📩 SMS:", decoded)

            except:
                pass

            time.sleep(0.05)

    # =========================
    # SIGNAL
    # =========================
    def update_signal_loop(self):
        while self.running:
            try:
                self.ser.write(b"AT+CSQ\r")
                time.sleep(0.2)
                resp = self.ser.read_all().decode(errors="ignore")

                if "+CSQ:" in resp:
                    self.signal_level = int(resp.split("+CSQ:")[1].split(",")[0].strip())

            except:
                pass

            time.sleep(5)

    # =========================
    # CALLS
    # =========================
    def call_number(self, number):
        if self.call_sent:
            return

        self.outgoing_number = number
        self.state = self.STATE_OUTGOING

        print("📞 CALLING:", number)
        self.send_at("ATD" + number + ";")

        self.call_sent = True
        self.draw()

    def answer_call(self):
        print("📞 ANSWER")
        self.send_at("ATA")

        self.state = self.STATE_CALLING
        self.incoming_call = False
        self.draw()

    def hangup(self):
        print("📴 HANGUP")
        self.send_at("ATH")

        self.state = self.STATE_IDLE
        self.call_sent = False
        self.incoming_call = False
        self.number = ""
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
    # HOOK
    # =========================
    def check_hook(self):
        raw = GPIO.input(self.HOOK_IN)

        if raw != self.stable_hook:
            self.stable_hook = raw

            if raw == GPIO.LOW:
                print("📞 HOOK OFF")
                if self.incoming_call:
                    self.answer_call()
                else:
                    n = self.format_number(self.number)
                    if n:
                        self.call_number(n)
            else:
                print("📴 HOOK ON")
                self.hangup()

        self.after(50, self.check_hook)

    # =========================
    # MENU + SMS 📩
    # =========================
    def open_menu(self):
        self.state = self.STATE_MENU
        self.draw()

    def open_sms(self):
        self.state = self.STATE_SMS
        self.draw()

    def close_menu(self):
        self.state = self.STATE_IDLE
        self.draw()

    # =========================
    # MAX
    # =========================
    def open_max(self):
        print("🌐 OPEN MAX")

        self.withdraw()  # скрываем телефон UI

        subprocess.Popen([
            "chromium",
            "--kiosk",
            "--noerrdialogs",
            "--disable-session-crashed-bubble",
            MAX_URL
        ])

        # вернуть UI через 10 сек (для теста)
        self.after(10000, self.deiconify)

    # =========================
    # DRAW
    # =========================
    def draw(self):
        self.canvas.delete("all")
        cx, cy = 400, 400

        # SMS SCREEN 📩
        if self.state == self.STATE_SMS:
            self.canvas.create_text(cx, 80, text="SMS",
                                    fill="white",
                                    font=("Arial", 30, "bold"))

            y = 150
            for msg in self.sms_list[-5:]:
                self.canvas.create_text(cx, y, text=msg,
                                        fill="lightgreen",
                                        font=("Arial", 16))
                y += 80

            return

        # MENU
        if self.state == self.STATE_MENU:
            self.canvas.create_text(cx, 120, text="МЕНЮ",
                                    fill="white",
                                    font=("Arial", 36, "bold"))

            self.canvas.create_rectangle(200, 220, 600, 300,
                                         fill="#1f2937", tags="max")
            self.canvas.create_text(cx, 260, text="MAX",
                                    fill="white", tags="max")

            self.canvas.create_rectangle(200, 340, 600, 420,
                                         fill="#1f2937", tags="sms")
            self.canvas.create_text(cx, 380, text="SMS",
                                    fill="white", tags="sms")

            self.canvas.tag_bind("max", "<Button-1>", lambda e: self.open_max())
            self.canvas.tag_bind("sms", "<Button-1>", lambda e: self.open_sms())

            return

        # MAIN DIAL (оставлено без изменений)
        self.canvas.create_oval(5,5,795,795,fill="#020617")
        self.canvas.create_oval(40,40,760,760,fill="#111827")

        for d in self.digits:
            ang = self.angle_map[d] + self.angle_offset - self.dial_angle
            rad = math.radians(ang)
            x = cx + 275 * math.cos(rad)
            y = cy - 275 * math.sin(rad)

            self.canvas.create_oval(x-45,y-45,x+45,y+45,fill="white")
            self.canvas.create_text(x,y,text=d,font=("Arial",24,"bold"))

        self.canvas.create_text(cx, cy-90,
                                text=self.number or "Номер",
                                fill="white")

        self.canvas.create_oval(350,350,450,450,fill="#1e293b",tags="menu")
        self.canvas.create_text(cx,cy,text="☰",fill="white",tags="menu")

        self.canvas.tag_bind("menu","<Button-1>",lambda e:self.open_menu())

    # ROTARY (без изменений)
    def on_press(self,e):
        self.selected_digit=self.detect_digit(e.x,e.y)
        if not self.selected_digit:return
        self.dragging=True
        self.start_angle=self.get_angle(e.x,e.y)
        self.dial_angle=0

    def on_drag(self,e):
        if not self.dragging:return
        self.dial_angle=(self.start_angle-self.get_angle(e.x,e.y))%360
        self.draw()

    def on_release(self,e):
        if self.dragging and self.dial_angle>=60:
            self.number+=self.selected_digit
        self.dragging=False
        self.animate_back()

    def animate_back(self):
        if self.dial_angle<=0:
            self.dial_angle=0
            self.draw()
            return
        self.dial_angle-=18
        self.draw()
        self.after(10,self.animate_back)

    def get_angle(self,x,y):
        return (math.degrees(math.atan2(400-y,x-400))+360)%360

    def detect_digit(self,x,y):
        best=None;bd=1e9
        for d,a in self.angle_map.items():
            rad=math.radians(a+self.angle_offset)
            dx=400+275*math.cos(rad)
            dy=400-275*math.sin(rad)
            dist=(dx-x)**2+(dy-y)**2
            if dist<bd:best=d;bd=dist
        return best if bd<4900 else None


if __name__=="__main__":
    app=RetroPhoneApp()
    app.mainloop()
