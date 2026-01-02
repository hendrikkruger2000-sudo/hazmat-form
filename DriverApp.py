# DriverApp.py — Hazmat Dashboard-Parity Edition (Crash-proof, complete)

import json
import requests
import numpy as np

# Optional heavy deps: guard to avoid hard crash if missing at runtime
try:
    import cv2
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

try:
    from pyzbar.pyzbar import decode as pyzbar_decode
    HAS_PYZBAR = True
except Exception:
    HAS_PYZBAR = False

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle, Line, RoundedRectangle
from kivy.uix.camera import Camera
from kivy_garden.mapview import MapView, MapMarker
from plyer import gps
from geopy.geocoders import Nominatim

BACKEND_URL = "https://hazmat-collection.onrender.com"

DRIVER_CREDENTIALS = {
    "Nkosa": {"password": "NK", "code": "NK"},
    "Rangwa": {"password": "KR", "code": "KR"}
}

# Palette (matches dashboard)
BG_WINDOW = (0.945, 0.972, 0.914, 1)      # #F1F8E9
BG_CARD   = (1, 1, 1, 1)                  # white
BORDER_SOFT = (0.784, 0.902, 0.788, 1)    # #C8E6C9
TEXT_PRIMARY = (0.2, 0.2, 0.2, 1)         # #333333
TEXT_ACCENT  = (0.18, 0.49, 0.29, 1)      # #2E7D32
GREEN = (0.18, 0.49, 0.29, 1)
RED   = (0.83, 0.20, 0.20, 1)
BLUE  = (0.10, 0.46, 0.82, 1)
NEUTRAL = (0.3, 0.3, 0.3, 1)

# ---------- Styling helpers ----------
def apply_light_background(widget):
    widget.canvas.before.clear()
    with widget.canvas.before:
        Color(*BG_WINDOW)
        bg_rect = Rectangle(size=widget.size, pos=widget.pos)
    widget._bg_rect = bg_rect

    def _sync(inst, _):
        if getattr(inst, "_bg_rect", None):
            inst._bg_rect.size = inst.size
            inst._bg_rect.pos  = inst.pos
    widget.bind(size=_sync, pos=_sync)

def make_logo_header(height=70):
    container = BoxLayout(orientation='vertical', size_hint_y=None, height=height+16, padding=(0,8,0,8))
    apply_light_background(container)
    logo = Image(source='static/logo.png', size_hint=(1,None), height=height)
    container.add_widget(logo)
    return container

def make_nav_bar(on_switch, on_logout):
    bar = BoxLayout(size_hint_y=None, height=56, spacing=10, padding=(20,8,20,8))
    btn_coll = Button(text="📦 Collections", background_color=RED)
    btn_coll.bind(on_press=lambda _: on_switch("collections"))
    btn_del = Button(text="✅ Deliveries", background_color=GREEN)
    btn_del.bind(on_press=lambda _: on_switch("deliveries"))
    btn_out = Button(text="🔓 Logout", background_color=NEUTRAL)
    btn_out.bind(on_press=lambda _: on_logout())
    bar.add_widget(btn_coll); bar.add_widget(btn_del); bar.add_widget(btn_out)
    return bar

def make_job_card(job, on_start, on_scan):
    company = job.get("company") if isinstance(job, dict) else str(job)
    address = job.get("address", "") if isinstance(job, dict) else ""
    ref     = job.get("hazjnb_ref", "") if isinstance(job, dict) else ""

    card = BoxLayout(orientation='vertical', size_hint_y=None, height=150, padding=16, spacing=10)
    with card.canvas.before:
        Color(*BG_CARD)
        bg = RoundedRectangle(radius=[10,10,10,10], size=card.size, pos=card.pos)
    with card.canvas.after:
        Color(*BORDER_SOFT)
        border = RoundedRectangle(radius=[10,10,10,10], size=card.size, pos=card.pos)
    card._bg = bg; card._border = border

    def _sync(inst, _):
        if inst._bg:
            inst._bg.size, inst._bg.pos = inst.size, inst.pos
        if inst._border:
            inst._border.size, inst._border.pos = inst.size, inst.pos
    card.bind(size=_sync, pos=_sync)

    title    = Label(text=company or "—", font_size=18, color=TEXT_PRIMARY, bold=True)
    subtitle = Label(text=address or "—", font_size=14, color=TEXT_PRIMARY)

    btn_row  = BoxLayout(size_hint_y=None, height=44, spacing=12)
    start_btn = Button(text="Start", background_color=BLUE)
    scan_btn  = Button(text="Scan",  background_color=GREEN)
    start_btn.bind(on_press=lambda _: on_start(job))
    scan_btn.bind(on_press=lambda _: on_scan(ref))
    btn_row.add_widget(start_btn); btn_row.add_widget(scan_btn)

    card.add_widget(title); card.add_widget(subtitle); card.add_widget(btn_row)
    return card

# ---------- Data sanitizers ----------
def _sanitize_jobs(raw):
    if raw is None: return []
    if isinstance(raw, dict): return [raw]
    if isinstance(raw, list):
        return [j if isinstance(j, dict) else {"company": str(j), "address": "", "hazjnb_ref": ""} for j in raw]
    if isinstance(raw, str):
        try:
            return _sanitize_jobs(json.loads(raw))
        except Exception:
            return [{"company": raw, "address": "", "hazjnb_ref": ""}]
    return []

def _normalize_job_fields(job):
    if not isinstance(job, dict): return job
    if "delivery_company" in job and "company" not in job:
        job["company"] = job["delivery_company"]
    if "delivery_address" in job and "address" not in job:
        job["address"] = job["delivery_address"]
    return job

# ---------- Screens ----------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', padding=40, spacing=24)
        apply_light_background(root)
        root.add_widget(make_logo_header())
        root.add_widget(Label(text="Driver Login", font_size=24, bold=True, color=TEXT_ACCENT))
        self.username = TextInput(hint_text='Driver Code', multiline=False, background_color=BG_CARD, foreground_color=TEXT_PRIMARY)
        self.password = TextInput(hint_text='Password',   multiline=False, password=True, background_color=BG_CARD, foreground_color=TEXT_PRIMARY)
        root.add_widget(self.username); root.add_widget(self.password)
        login_btn = Button(text='Login', background_color=GREEN, size_hint_y=None, height=48)
        login_btn.bind(on_press=self.login)
        root.add_widget(login_btn)
        self.add_widget(root)

    def login(self, _):
        u = self.username.text.strip(); p = self.password.text.strip()
        if u in DRIVER_CREDENTIALS and DRIVER_CREDENTIALS[u]["password"] == p:
            self.manager.driver_code = DRIVER_CREDENTIALS[u]["code"]
            self.manager.current = "collections"
        else:
            Popup(title="Login Failed", content=Label(text="❌ Invalid credentials", color=RED),
                  size_hint=(None, None), size=(320, 180)).open()

class BaseJobScreen(Screen):
    def __init__(self, title, endpoint, **kwargs):
        super().__init__(**kwargs)
        self.endpoint = endpoint
        root = BoxLayout(orientation='vertical', padding=20, spacing=16)
        apply_light_background(root)
        root.add_widget(make_logo_header())
        root.add_widget(Label(text=title, color=TEXT_ACCENT, font_size=20, bold=True))
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, spacing=12, size_hint_y=None, padding=(20, 6, 20, 6))
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)
        root.add_widget(make_nav_bar(self.switch_to, self.logout))
        self.add_widget(root)

    def on_enter(self):
        Clock.schedule_once(self.refresh_jobs, 0.15)

    def switch_to(self, name):
        self.manager.current = name

    def logout(self):
        self.manager.driver_code = None
        self.manager.current = "login"

    def refresh_jobs(self, _):
        self.grid.clear_widgets()
        try:
            code = getattr(self.manager, "driver_code", None)
            if not code:
                self.grid.add_widget(Label(text="No driver code — please login", color=RED, size_hint_y=None, height=28))
                return

            res = requests.get(f"{BACKEND_URL}/{self.endpoint}/{code}", timeout=10)
            try:
                data = res.json()
            except ValueError:
                data = res.text
            jobs = [_normalize_job_fields(j) for j in _sanitize_jobs(data)]

            if not jobs:
                self.grid.add_widget(Label(text="No jobs assigned", color=TEXT_PRIMARY, size_hint_y=None, height=28))
                return

            for job in jobs:
                self.grid.add_widget(make_job_card(job, self.start_collection, self.scan_qr))
        except Exception as e:
            self.grid.add_widget(Label(text=f"❌ Failed to load jobs: {e}", color=RED, size_hint_y=None, height=28))

    def start_collection(self, job):
        self.manager.active_job = job
        self.manager.current = "map"
        try:
            requests.post(f"{BACKEND_URL}/update_status", json={
                "ref": job.get("hazjnb_ref", ""),
                "status": "in_progress",
                "driver_id": self.manager.driver_code
            }, timeout=10)
        except Exception as e:
            Popup(title="Status Error",
                  content=Label(text=f"❌ Failed to update status: {e}", color=RED),
                  size_hint=(None, None), size=(320, 200)).open()

    def scan_qr(self, expected_ref):
        self.manager.collection_ref = expected_ref
        self.manager.current = "camera"

class MapScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', spacing=10, padding=10)
        apply_light_background(root)

        self.mapview = MapView(zoom=12, lat=-26.2, lon=28.3)
        root.add_widget(self.mapview)

        back = Button(text="⬅️ Back to Jobs", size_hint_y=None, height=48, background_color=NEUTRAL)
        back.bind(on_press=lambda _: setattr(self.manager, 'current', 'collections'))
        root.add_widget(back)

        self.add_widget(root)

        # state
        self.driver_marker = None
        self.collection_marker = None
        self.route_line = None
        self.driver_lat = None
        self.driver_lon = None

    def on_enter(self):
        self.geocode_collection()
        self.start_gps()

    def geocode_collection(self):
        try:
            job = getattr(self.manager, 'active_job', None)
            if not job or "address" not in job:
                return
            address = f"{job['address']}, Gauteng, South Africa"
            geolocator = Nominatim(user_agent="hazmat_driver")
            location = geolocator.geocode(address, timeout=10)
            if location:
                lat, lon = location.latitude, location.longitude
                self.collection_marker = MapMarker(lat=lat, lon=lon)
                self.mapview.add_marker(self.collection_marker)
                self.mapview.center_on(lat, lon)
            else:
                print(f"❌ Geocoding failed for: {address}")
        except Exception as e:
            print(f"❌ Geocode error: {e}")

    def start_gps(self):
        try:
            gps.configure(on_location=self.update_driver_location)
            gps.start()
        except NotImplementedError:
            print("GPS not available on this platform")
        except Exception as e:
            print(f"❌ GPS start error: {e}")

    def update_driver_location(self, **kwargs):
        self.driver_lat = kwargs.get('lat')
        self.driver_lon = kwargs.get('lon')
        if not self.driver_lat or not self.driver_lon:
            return
        if self.driver_marker:
            self.mapview.remove_marker(self.driver_marker)
        self.driver_marker = MapMarker(lat=self.driver_lat, lon=self.driver_lon)
        self.mapview.add_marker(self.driver_marker)
        self.draw_route()

    def draw_route(self):
        if not self.driver_lat or not self.driver_lon or not self.collection_marker:
            return
        x1, y1 = self.mapview.get_window_xy_from(lat=self.driver_lat, lon=self.driver_lon, zoom=self.mapview.zoom)
        x2, y2 = self.mapview.get_window_xy_from(lat=self.collection_marker.lat, lon=self.collection_marker.lon, zoom=self.mapview.zoom)
        if self.route_line:
            try:
                self.mapview.canvas.remove(self.route_line)
            except Exception:
                pass
        with self.mapview.canvas:
            Color(*RED)
            self.route_line = Line(points=[x1, y1, x2, y2], width=2)

class CameraScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        root = BoxLayout(orientation='vertical', spacing=10, padding=10)
        apply_light_background(root)

        self.camera = None
        self.info_label = Label(text="", color=TEXT_PRIMARY, size_hint_y=None, height=28)

        try:
            cam = Camera(play=False, resolution=(640, 480))
            cam.play = True
            Clock.schedule_once(lambda *_: setattr(cam, 'play', False), 0)
            self.camera = cam
            root.add_widget(cam)
        except Exception as e:
            root.add_widget(Label(text="❌ No camera detected", font_size=18, color=RED))
            print(f"Camera init failed: {e}")

        # Capability hints
        if not HAS_CV2:
            root.add_widget(Label(text="⚠️ OpenCV not available — using raw RGBA", color=RED, size_hint_y=None, height=28))
        if not HAS_PYZBAR:
            root.add_widget(Label(text="⚠️ Pyzbar not available — QR decode disabled", color=RED, size_hint_y=None, height=28))

        root.add_widget(self.info_label)
        self.add_widget(root)
        self.scanning = False

    def on_enter(self):
        self.info_label.text = "Align QR code within camera view"
        if self.camera:
            self.camera.play = True
            self.scanning = True
            Clock.schedule_interval(self.scan_texture, 1 / 10)  # 10 FPS

    def on_leave(self):
        if self.camera:
            self.camera.play = False
        self.scanning = False
        Clock.unschedule(self.scan_texture)

    def scan_texture(self, dt):
        if not self.scanning or not self.camera or not self.camera.texture:
            return
        texture = self.camera.texture
        size = texture.size
        pixels = texture.pixels
        if not pixels or size[0] <= 0 or size[1] <= 0:
            return

        # Convert RGBA -> Grayscale if OpenCV available, else keep RGBA
        img = np.frombuffer(pixels, np.uint8).reshape(size[1], size[0], 4)
        if HAS_CV2:
            gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)
            frame_for_decode = gray
        else:
            frame_for_decode = img  # pyzbar can sometimes read RGBA; not guaranteed

        if not HAS_PYZBAR:
            # No decoder — show info once
            self.info_label.text = "QR decode not available (pyzbar missing)"
            return

        try:
            barcodes = pyzbar_decode(frame_for_decode)
        except Exception as e:
            self.info_label.text = f"Decode error: {e}"
            return

        for barcode in barcodes:
            qr_data = barcode.data.decode('utf-8')
            expected_ref = getattr(self.manager, 'collection_ref', None)
            if expected_ref and qr_data.endswith(expected_ref):
                self.scanning = False
                Clock.unschedule(self.scan_texture)
                self.confirm_scan(expected_ref)
                return

    def confirm_scan(self, ref):
        try:
            res = requests.post(f"{BACKEND_URL}/scan_qr", json={
                "ref": ref,
                "driver_id": self.manager.driver_code
            }, timeout=10)
            try:
                payload = res.json()
                timestamp = payload.get("timestamp", "")
            except Exception:
                timestamp = ""
            Popup(title="Scan Confirmed",
                  content=Label(text=f"✅ QR scan confirmed\n{timestamp}", color=TEXT_PRIMARY),
                  size_hint=(None, None), size=(320, 220)).open()
        except Exception as e:
            Popup(title="Scan Error",
                  content=Label(text=f"❌ Scan error: {e}", color=RED),
                  size_hint=(None, None), size=(320, 220)).open()
        self.manager.current = "collections"

class DriverApp(App):
    def build(self):
        sm = ScreenManager()
        sm.driver_code = None
        sm.collection_ref = None
        sm.active_job = None

        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(BaseJobScreen(name="collections", title="📦 Assigned Collections", endpoint="driver"))
        sm.add_widget(BaseJobScreen(name="deliveries",  title="✅ Deliveries",            endpoint="deliveries"))
        sm.add_widget(MapScreen(name="map"))
        sm.add_widget(CameraScreen(name="camera"))
        sm.current = "login"
        return sm

if __name__ == "__main__":
    DriverApp().run()
