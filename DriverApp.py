# DriverApp.py — Mythic Embedded Map Edition
import requests, urllib.parse
from pyzbar.pyzbar import decode
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
from kivy.graphics import Color, Rectangle
from kivy.uix.camera import Camera
from kivy_garden.mapview import MapView, MapMarker
from plyer import gps
import requests
import numpy as np
from pyzbar.pyzbar import decode
from kivy.graphics.texture import Texture
from geopy.geocoders import Nominatim
import cv2


DRIVER_CREDENTIALS = {
    "Nkosa": {"password": "NK", "code": "NK"},
    "Rangwa": {"password": "KR", "code": "KR"}
}

BACKEND_URL = "https://hazmat-collection.onrender.com"

# -------------------- Login Screen --------------------
class LoginScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=40, spacing=20)
        logo = Image(source='static/logo.png', size_hint=(1, 0.3), allow_stretch=True, keep_ratio=False)
        layout.add_widget(logo)
        layout.add_widget(Label(text='Hazmat Driver Login', font_size=24, bold=True, color=(1, 1, 1, 1)))
        self.username = TextInput(hint_text='Driver Code', multiline=False)
        self.password = TextInput(hint_text='Password', multiline=False, password=True)
        layout.add_widget(self.username)
        layout.add_widget(self.password)
        login_btn = Button(text='Login', background_color=(0.8, 0, 0, 1))
        login_btn.bind(on_press=self.login)
        layout.add_widget(login_btn)
        self.add_widget(layout)

    def login(self, instance):
        username = self.username.text.strip()
        password = self.password.text.strip()
        if username in DRIVER_CREDENTIALS and DRIVER_CREDENTIALS[username]["password"] == password:
            self.manager.driver_code = DRIVER_CREDENTIALS[username]["code"]
            self.manager.current = "collections"
        else:
            Popup(title="Login Failed", content=Label(text="❌ Invalid credentials"),
                  size_hint=(None, None), size=(300, 200)).open()

# -------------------- Collections Screen --------------------
class CollectionsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        self.set_dark_theme(self.layout)
        logo = Image(source="static/logo.png", size_hint=(1, 0.2), allow_stretch=True, keep_ratio=False)
        self.layout.add_widget(logo)
        self.layout.add_widget(Label(text="📦 Assigned Collections", font_size=22, bold=True, color=(1, 1, 1, 1)))
        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, spacing=10, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        self.layout.add_widget(self.scroll)
        menu = BoxLayout(size_hint_y=None, height=60, spacing=10)
        for label, color in [("📦 Collections", (0.8, 0, 0, 1)), ("✅ Deliveries", (0, 0.8, 0, 1)), ("🔓 Logout", (0.3, 0.3, 0.3, 1))]:
            btn = Button(text=label, background_color=color)
            btn.bind(on_press=self.switch_to if label != "🔓 Logout" else self.logout)
            menu.add_widget(btn)
        self.layout.add_widget(menu)
        self.add_widget(self.layout)

    def on_enter(self):
        Clock.schedule_once(self.refresh_jobs, 0.5)

    def switch_to(self, instance):
        self.manager.current = instance.text.strip().split()[1].lower()

    def logout(self, instance):
        self.manager.driver_code = None
        self.manager.current = "login"

    def set_dark_theme(self, layout):
        layout.canvas.before.clear()
        with layout.canvas.before:
            Color(0.11, 0.11, 0.11, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
            layout.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.size = instance.size
        self.rect.pos = instance.pos

    def refresh_jobs(self, dt):
        self.grid.clear_widgets()
        try:
            res = requests.get(f"{BACKEND_URL}/driver/{self.manager.driver_code}")
            jobs = res.json()
            if not jobs:
                self.grid.add_widget(Label(text="No collections assigned", color=(0.6, 0.6, 0.6, 1)))
                return
            for job in jobs:
                card = BoxLayout(orientation='vertical', size_hint_y=None, height=120, padding=10, spacing=5)
                with card.canvas.before:
                    Color(0.15, 0.15, 0.15, 1)
                    rect = Rectangle(size=card.size, pos=card.pos)
                    card.bind(size=lambda inst, val: setattr(rect, 'size', val),
                              pos=lambda inst, val: setattr(rect, 'pos', val))
                card.add_widget(Label(text=job["company"], font_size=18, color=(1, 1, 1, 1)))
                card.add_widget(Label(text=job["address"], font_size=14, color=(0.7, 0.7, 0.7, 1)))
                btn_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
                start_btn = Button(text="Start", background_color=(0.8, 0, 0, 1))
                scan_btn = Button(text="Scan", background_color=(0, 0.8, 0, 1))
                start_btn.bind(on_press=lambda _, j=job: self.start_collection(j))
                scan_btn.bind(on_press=lambda _, r=job["hazjnb_ref"]: self.scan_qr(r))
                btn_row.add_widget(start_btn)
                btn_row.add_widget(scan_btn)
                card.add_widget(btn_row)
                self.grid.add_widget(card)
        except Exception as e:
            self.grid.add_widget(Label(text=f"❌ Failed to load jobs: {e}", color=(1, 0.5, 0.5, 1)))

    def start_collection(self, job):
        self.manager.active_job = job
        self.manager.current = "map"
        try:
            requests.post(f"{BACKEND_URL}/update_status", json={
                "ref": job["hazjnb_ref"],
                "status": "in_progress",
                "driver_id": self.manager.driver_code
            })
        except Exception as e:
            Popup(title="Status Error",
                  content=Label(text=f"❌ Failed to update status: {e}"),
                  size_hint=(None, None), size=(300, 200)).open()

    def scan_qr(self, expected_ref):
        self.manager.collection_ref = expected_ref
        self.manager.current = "camera"

# -------------------- Deliveries Screen --------------------
class DeliveriesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        self.set_dark_theme(layout)
        logo = Image(source="static/logo.png", size_hint=(1, 0.2))
        layout.add_widget(logo)
        layout.add_widget(Label(text="✅ Delivery History", font_size=18, color=(1, 1, 1, 1)))
        layout.add_widget(Label(text="(Coming soon)", font_size=14, color=(0.7, 0.7, 0.7, 1)))
        menu = BoxLayout(size_hint_y=None, height=50, spacing=10)
        for label in ["📦 Collections", "✅ Deliveries", "🔓 Logout"]:
            btn = Button(text=label)
            btn.bind(on_press=self.switch_to_screen if "Logout" not in label else self.logout)
            menu.add_widget(btn)
        layout.add_widget(menu)
        self.add_widget(layout)

    def switch_to_screen(self, instance):
        self.manager.current = instance.text.strip().split()[1].lower()

    def logout(self, instance):
        self.manager.driver_code = None
        self.manager.current = "login"

    def set_dark_theme(self, layout):
        layout.canvas.before.clear()
        with layout.canvas.before:
            Color(0.11, 0.11, 0.11, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
            layout.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, instance, value):
        self.rect.size = instance.size
        self.rect.pos = instance.pos

class MapScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        self.mapview = MapView(zoom=12, lat=-26.2, lon=28.3)
        self.layout.add_widget(self.mapview)

        self.back_btn = Button(text="⬅️ Back to Jobs", size_hint_y=None, height=50, background_color=(0.3, 0.3, 0.3, 1))
        self.back_btn.bind(on_press=lambda _: setattr(self.manager, 'current', 'collections'))
        self.layout.add_widget(self.back_btn)

        self.add_widget(self.layout)

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
            job = self.manager.active_job
            if not job or "address" not in job:
                return
            address = f"{job['address']}, Gauteng, South Africa"
            geolocator = Nominatim(user_agent="hazmat_driver")
            location = geolocator.geocode(address)
            if location:
                lat, lon = location.latitude, location.longitude
                self.collection_marker = MapMarker(lat=lat, lon=lon)
                self.mapview.add_marker(self.collection_marker)
                self.mapview.center_on(lat, lon)
                self.collection_lat = lat
                self.collection_lon = lon
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

    def update_driver_location(self, **kwargs):
        self.driver_lat = kwargs['lat']
        self.driver_lon = kwargs['lon']
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
            self.mapview.canvas.remove(self.route_line)

        with self.mapview.canvas:
            Color(1, 0, 0, 1)
            self.route_line = Line(points=[x1, y1, x2, y2], width=2)



class CameraScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.layout = BoxLayout(orientation='vertical')
        self.camera = Camera(play=False, resolution=(640, 480))
        self.layout.add_widget(self.camera)
        self.add_widget(self.layout)
        self.scanning = False

    def on_enter(self):
        self.camera.play = True
        self.scanning = True
        Clock.schedule_interval(self.scan_texture, 1 / 10)  # Scan at 10 FPS

    def on_leave(self):
        self.camera.play = False
        self.scanning = False
        Clock.unschedule(self.scan_texture)

    def scan_texture(self, dt):
        if not self.scanning or not self.camera.texture:
            return

        texture = self.camera.texture
        size = texture.size
        pixels = texture.pixels

        # Convert texture to numpy array
        img = np.frombuffer(pixels, np.uint8).reshape(size[1], size[0], 4)
        gray = cv2.cvtColor(img, cv2.COLOR_RGBA2GRAY)

        for barcode in decode(gray):
            qr_data = barcode.data.decode('utf-8')
            expected_ref = self.manager.collection_ref
            if qr_data.endswith(expected_ref):
                self.scanning = False
                Clock.unschedule(self.scan_texture)
                self.confirm_scan(expected_ref)
                return

    def confirm_scan(self, ref):
        try:
            res = requests.post(f"{BACKEND_URL}/scan_qr", json={
                "ref": ref,
                "driver_id": self.manager.driver_code
            })
            timestamp = res.json().get("timestamp", "")
            self.show_popup("Scan Confirmed", f"✅ QR scan confirmed\n{timestamp}")
        except Exception as e:
            self.show_popup("Scan Error", f"❌ Scan error: {e}")
        self.manager.current = "collections"

    def show_popup(self, title, message):
        popup = Popup(title=title,
                      content=Label(text=message),
                      size_hint=(None, None), size=(300, 200))
        popup.open()


class DriverApp(App):
    def build(self):
        sm = ScreenManager()
        sm.driver_code = None
        sm.collection_ref = None
        sm.destination_address = None
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(CollectionsScreen(name="collections"))
        sm.add_widget(DeliveriesScreen(name="deliveries"))
        sm.add_widget(MapScreen(name="map"))
        sm.add_widget(CameraScreen(name="camera"))
        sm.current = "login"
        return sm

if __name__ == "__main__":
    DriverApp().run()