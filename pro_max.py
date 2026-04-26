import math
import subprocess
import tkinter as tk
import customtkinter as ctk


MAX_URL = "https://web.max.ru"


class RetroPhoneApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.overrideredirect(True)
        self.geometry("800x800+0+0")
        self.configure(fg_color="#050505")

        self.number = ""
        self.rotary_mode = True

        self.dragging = False
        self.start_angle = 0
        self.dial_angle = 0
        self.selected_digit = None
        self.required_rotation = 0

        self.angle_offset = 40
        self.stopper_angle = 315
        self.back_window = None

        self.base_positions = {
            "3": 132, "2": 111, "1": 90,
            "4": 153, "5": 180, "6": 207,
            "7": 234, "8": 261, "9": 288, "0": 315,
        }

        self.canvas = ctk.CTkCanvas(
            self, width=800, height=800,
            bg="#050505", highlightthickness=0
        )
        self.canvas.pack()

        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.draw()

    def draw(self):
        self.canvas.delete("all")
        cx, cy = 400, 400

        self.canvas.create_oval(5, 5, 795, 795, fill="#020617", outline="#020617")
        self.canvas.create_oval(65, 65, 735, 735, fill="#111827", outline="#2563eb", width=8)
        self.canvas.create_oval(95, 95, 705, 705, fill="#0f172a", outline="#1e40af", width=2)
        self.canvas.create_oval(235, 235, 565, 565, fill="#020617", outline="#38bdf8", width=5)

        self.draw_stopper(cx, cy)
        self.draw_digits(cx, cy)

        shown_number = self.number if self.number else "Номер"
        self.canvas.create_text(cx, cy - 75, text=shown_number, fill="#e5e7eb", font=("Arial", 24, "bold"))

        self.add_canvas_button("MAX", cx - 85, cy - 25, 170, 58, self.open_max, "#22c55e")
        self.add_canvas_button("⌫", cx - 85, cy + 50, 78, 50, self.backspace, "#2563eb")
        self.add_canvas_button("C", cx + 7, cy + 50, 78, 50, self.clear_number, "#dc2626")

        mode_text = "Диск: ВКЛ" if self.rotary_mode else "Диск: ВЫКЛ"
        self.canvas.create_text(cx, 575, text=mode_text, fill="#94a3b8", font=("Arial", 15, "bold"))
        self.add_canvas_button("⚙", 350, 590, 100, 48, self.toggle_rotary_mode, "#334155")

        self.add_call_button("☎", 145, 640, 115, self.answer_call, "#16a34a")
        self.add_call_button("✕", 540, 640, 115, self.end_call, "#dc2626")

        if self.dragging:
            self.draw_drag_arc(cx, cy)

    def draw_digits(self, cx, cy):
        r = 275
        for digit, base_angle in self.base_positions.items():
            current_angle = (base_angle - self.angle_offset - self.dial_angle) % 360
            rad = math.radians(current_angle)
            x = cx + r * math.cos(rad)
            y = cy - r * math.sin(rad)

            self.canvas.create_oval(x - 45, y - 45, x + 45, y + 45, fill="#020617", outline="#1e293b", width=2)
            self.canvas.create_oval(x - 40, y - 40, x + 40, y + 40, fill="#f8fafc", outline="#94a3b8", width=3)
            self.canvas.create_text(x, y, text=digit, fill="#020617", font=("Arial", 30, "bold"))

    def draw_stopper(self, cx, cy):
        rad = math.radians(self.stopper_angle)
        x1 = cx + 255 * math.cos(rad)
        y1 = cy - 255 * math.sin(rad)
        x2 = cx + 350 * math.cos(rad)
        y2 = cy - 350 * math.sin(rad)

        self.canvas.create_line(x1, y1, x2, y2, fill="#d1d5db", width=16, capstyle="round")
        self.canvas.create_line(x1, y1, x2, y2, fill="#111827", width=4, capstyle="round")
        self.canvas.create_oval(x2 - 18, y2 - 18, x2 + 18, y2 + 18, fill="#d1d5db", outline="#111827", width=3)

    def draw_drag_arc(self, cx, cy):
        if self.selected_digit:
            self.canvas.create_arc(
                cx - 315, cy - 315, cx + 315, cy + 315,
                start=self.get_digit_start_angle(self.selected_digit),
                extent=-self.dial_angle,
                style="arc",
                outline="#38bdf8",
                width=12
            )

    def get_digit_start_angle(self, digit):
        return (self.base_positions[digit] - self.angle_offset) % 360

    def get_required_rotation(self, digit):
        start = self.get_digit_start_angle(digit)
        return (start - self.stopper_angle) % 360

    def on_press(self, event):
        digit = self.detect_digit(event.x, event.y)
        if digit is None:
            return

        if not self.rotary_mode:
            self.number += digit
            self.draw()
            return

        self.selected_digit = digit
        self.required_rotation = self.get_required_rotation(digit)
        self.dragging = True
        self.start_angle = self.get_angle(event.x, event.y)
        self.dial_angle = 0
        self.draw()

    def on_drag(self, event):
        if not self.dragging:
            return

        current = self.get_angle(event.x, event.y)
        delta = self.start_angle - current
        if delta < 0:
            delta += 360

        self.dial_angle = min(delta, self.required_rotation)
        self.draw()

    def on_release(self, event):
        if not self.dragging:
            return

        digit = self.selected_digit
        reached_stopper = self.dial_angle >= self.required_rotation - 8

        self.dragging = False
        self.selected_digit = None

        if reached_stopper:
            self.number += digit

        self.animate_return()

    def animate_return(self):
        if self.dial_angle <= 0:
            self.dial_angle = 0
            self.draw()
            return

        self.dial_angle -= 12
        if self.dial_angle < 0:
            self.dial_angle = 0

        self.draw()
        self.after(10, self.animate_return)

    def detect_digit(self, x, y):
        cx, cy = 400, 400
        r = 275
        best_digit = None
        best_dist = 999999

        for digit, base_angle in self.base_positions.items():
            angle = (base_angle - self.angle_offset - self.dial_angle) % 360
            rad = math.radians(angle)
            dx = cx + r * math.cos(rad)
            dy = cy - r * math.sin(rad)
            dist = (dx - x) ** 2 + (dy - y) ** 2

            if dist < best_dist:
                best_dist = dist
                best_digit = digit

        return best_digit if best_dist <= 55 ** 2 else None

    def get_angle(self, x, y):
        dx = x - 400
        dy = 400 - y
        angle = math.degrees(math.atan2(dy, dx))
        return angle + 360 if angle < 0 else angle

    def add_canvas_button(self, text, x, y, w, h, command, color):
        tag = f"btn_{text}_{x}_{y}"
        r = h // 2

        self.canvas.create_oval(x, y, x + h, y + h, fill=color, outline="", tags=(tag,))
        self.canvas.create_oval(x + w - h, y, x + w, y + h, fill=color, outline="", tags=(tag,))
        self.canvas.create_rectangle(x + r, y, x + w - r, y + h, fill=color, outline="", tags=(tag,))
        self.canvas.create_text(x + w / 2, y + h / 2, text=text, fill="white", font=("Arial", 24, "bold"), tags=(tag,))
        self.canvas.tag_bind(tag, "<Button-1>", lambda e: command())

    def add_call_button(self, text, x, y, size, command, color):
        tag = f"call_{text}_{x}_{y}"
        self.canvas.create_oval(x, y, x + size, y + size, fill=color, outline="#f8fafc", width=2, tags=(tag,))
        self.canvas.create_text(x + size / 2, y + size / 2, text=text, fill="white", font=("Arial", 42, "bold"), tags=(tag,))
        self.canvas.tag_bind(tag, "<Button-1>", lambda e: command())

    def toggle_rotary_mode(self):
        self.rotary_mode = not self.rotary_mode
        self.draw()

    def backspace(self):
        self.number = self.number[:-1]
        self.draw()

    def clear_number(self):
        self.number = ""
        self.draw()

    def answer_call(self):
        print("ANSWER CALL")

    def end_call(self):
        print("END CALL")
        self.clear_number()

    def open_max(self):
        self.withdraw()

        subprocess.Popen([
            "chromium",
            "--app=" + MAX_URL,
            "--window-size=600,600",
            "--window-position=100,100",
            "--touch-events=enabled",
            "--enable-features=TouchpadOverscrollHistoryNavigation",
            "--noerrdialogs",
            "--disable-infobars",
            "--disable-session-crashed-bubble"
            "--touch-events=enabled",
            "--enable-features=TouchpadOverscrollHistoryNavigation,OverlayScrollbar",
            "--enable-blink-features=TouchEventFeatureDetection",
            "--disable-features=Translate",
    ])

        self.after(1200, self.show_back_window)

    def show_back_window(self):
        if self.back_window is not None:
            try:
                self.back_window.destroy()
            except Exception:
                pass

        transparent = "#ff00ff"

        self.back_window = tk.Toplevel(self)
        self.back_window.overrideredirect(True)
        self.back_window.attributes("-topmost", True)
        self.back_window.geometry("220x80+290+705")
        self.back_window.configure(bg=transparent)

        try:
            self.back_window.attributes("-transparentcolor", transparent)
        except Exception:
            pass

        c = tk.Canvas(
            self.back_window,
            width=220,
            height=80,
            bg=transparent,
            highlightthickness=0,
            bd=0
        )
        c.pack()

        tag = "back_btn"

        c.create_oval(5, 8, 75, 72, fill="#dc2626", outline="", tags=(tag,))
        c.create_oval(145, 8, 215, 72, fill="#dc2626", outline="", tags=(tag,))
        c.create_rectangle(40, 8, 180, 72, fill="#dc2626", outline="", tags=(tag,))
        c.create_text(110, 40, text="← Назад", fill="white", font=("Arial", 22, "bold"), tags=(tag,))

        c.tag_bind(tag, "<Button-1>", lambda e: self.close_max())

    def close_max(self):
        subprocess.call(["pkill", "chromium"])

        if self.back_window is not None:
            try:
                self.back_window.destroy()
            except Exception:
                pass
            self.back_window = None

        self.deiconify()
        self.focus_force()
        self.draw()


if __name__ == "__main__":
    app = RetroPhoneApp()
    app.mainloop()
