from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.clock import Clock
from kivy.graphics.texture import Texture
import requests
import cv2
from pyzbar.pyzbar import decode
import threading
import websocket
import json
import threading
from kivy.uix.popup import Popup

# Replace with your actual backend IP
BACKEND_URL = "http://192.168.10.5:5000"

def start_socket_listener(screen):
    def on_message(ws, message):
        data = json.loads(message)
        if "ref" in data:
            ref = data["ref"]
            popup = Popup(title="📦 New Job Assigned",
                          content=Label(text=f"Ref: {ref}"),
                          size_hint=(0.8, 0.4))
            popup.open()
            screen.fetch_jobs()

    def on_open(ws):
        ws.send(json.dumps({"driver_id": "DRIVER001", "type": "connect_driver"}))

    ws = websocket.WebSocketApp("ws://192.168.10.5:5000/socket.io/?EIO=4&transport=websocket",
                                on_message=on_message,
                                on_open=on_open)
    threading.Thread(target=ws.run_forever, daemon=True).start()

# -------------------------------
# Job List Screen
# -------------------------------
class JobScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical')
        self.label = Label(text="Fetching jobs...", font_size=18)
        layout.add_widget(self.label)

        refresh_btn = Button(text="🔄 Refresh Jobs", size_hint=(1, 0.2))
        refresh_btn.bind(on_press=self.fetch_jobs)
        layout.add_widget(refresh_btn)

        scan_btn = Button(text="📷 Scan Waybill", size_hint=(1, 0.2))
        scan_btn.bind(on_press=self.go_to_qr)
        layout.add_widget(scan_btn)

        self.add_widget(layout)
        self.fetch_jobs()
        start_socket_listener(self)

    def fetch_jobs(self, instance=None):
        try:
            res = requests.get(f"{BACKEND_URL}/get_jobs?driver_id=DRIVER001")
            jobs = res.json().get("jobs", [])
            if jobs:
                self.label.text = "\n".join([f"{j['ref']} - {j['status']}" for j in jobs])
            else:
                self.label.text = "No jobs assigned."
        except Exception as e:
            self.label.text = f"Error fetching jobs: {e}"

    def go_to_qr(self, instance):
        self.manager.current = "qr"

# -------------------------------
# QR Scanner Screen
# -------------------------------
class QRScanScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.img = Image()
        self.add_widget(self.img)
        self.capture = None

    def on_enter(self):
        self.capture = cv2.VideoCapture(0)
        Clock.schedule_interval(self.update, 1.0 / 30.0)

    def on_leave(self):
        if self.capture:
            self.capture.release()
            self.capture = None
        Clock.unschedule(self.update)

    def update(self, dt):
        if not self.capture:
            return
        ret, frame = self.capture.read()
        if ret:
            self.img.texture = self.texture_from_frame(frame)
            for code in decode(frame):
                ref = code.data.decode("utf-8")
                threading.Thread(target=self.send_ref, args=(ref,)).start()
                self.manager.current = "job"

    def texture_from_frame(self, frame):
        buf = cv2.flip(frame, 0).tobytes()
        texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
        texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
        return texture

    def send_ref(self, ref):
        try:
            res = requests.post(f"{BACKEND_URL}/scan_qr", json={"ref": ref, "driver_id": "DRIVER001"})
            print("✅ Scan confirmed:", res.text)
        except Exception as e:
            print("❌ Scan error:", e)

# -------------------------------
# App Entry Point
# -------------------------------
class HazmatDriverApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(JobScreen(name="job"))
        sm.add_widget(QRScanScreen(name="qr"))
        return sm

if __name__ == "__main__":
    HazmatDriverApp().run()