import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QDialog,
    QTabWidget, QLineEdit, QTextEdit, QSizePolicy, QScrollArea,
    QHeaderView, QFileDialog, QDateEdit
)
import threading, requests
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView

from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QGridLayout
import requests
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QSplitter
from PyQt6.QtGui import QPalette, QColor
class TablePoller(QObject):
    collections_updated = pyqtSignal(list)
    assigned_updated = pyqtSignal(list)
    completed_updated = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer()
        self.timer.timeout.connect(self.poll_all)
        self.timer.start(1500)  # 🔁 Increase to 1.5s for stability
        self.is_polling = False

    def poll_all(self):
        if self.is_polling:
            return
        self.is_polling = True
        threading.Thread(target=self._poll_worker, daemon=True).start()

    def _poll_worker(self):
        self.fetch_collections()
        self.fetch_assigned()
        self.fetch_completed()
        self.is_polling = False

    def fetch_collections(self):
        try:
            r = requests.get("https://hazmat-collection.onrender.com/ops/collections", timeout=2)
            if r.status_code == 200:
                self.collections_updated.emit(r.json())
        except Exception as e:
            print("❌ collections fetch failed:", e)

    def fetch_assigned(self):
        try:
            r = requests.get("https://hazmat-collection.onrender.com/ops/assigned", timeout=2)
            if r.status_code == 200:
                self.assigned_updated.emit(r.json())
        except Exception as e:
            print("❌ assigned fetch failed:", e)

    def fetch_completed(self):
        try:
            r = requests.get("https://hazmat-collection.onrender.com/ops/completed", timeout=5)
            if r.status_code == 200:
                self.completed_updated.emit(r.json())
        except Exception as e:
            print("❌ completed fetch failed:", e)


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hazmat Global Login")
        self.setFixedSize(500, 420)

        # Global style (matches dashboard aesthetics)
        self.setStyleSheet("""
            QDialog {
                background-color: #F1F8E9;
            }
            QLabel {
                color: #2E7D32;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Segoe UI';
            }
            QPushButton {
                background-color: #2E7D32;
                color: white;
                padding: 8px;
                border-radius: 6px;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QLineEdit {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #C8E6C9;
                padding: 8px;
                border-radius: 4px;
                font-size: 14px;
                font-family: 'Segoe UI';
            }
        """)

        # ✅ Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        # 🔰 Logo
        logo = QLabel()
        pixmap = QPixmap("static/logo.png")
        logo.setPixmap(pixmap.scaledToHeight(70, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # 🧾 Title
        title = QLabel("Hazmat Global Support Services")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 🔐 Credential Card
        form_card = QWidget()
        form_card.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #C8E6C9;
                border-radius: 10px;
            }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setContentsMargins(20, 20, 20, 20)
        form_layout.setSpacing(15)

        # Prompt
        prompt = QLabel("Enter your credentials:")
        prompt.setStyleSheet("color: #333333; font-size: 14px; font-family: 'Segoe UI';")
        form_layout.addWidget(prompt)

        # Username
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        form_layout.addWidget(self.username_input)

        # Password
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addWidget(self.password_input)

        # Login button
        self.login_btn = QPushButton("Login")
        self.login_btn.setFixedHeight(40)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #2E7D32;
                color: white;
                font-weight: bold;
                font-size: 14px;
                font-family: 'Segoe UI';
                border-radius: 6px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
        """)
        self.login_btn.clicked.connect(self.handle_login)
        form_layout.addWidget(self.login_btn)

        # Error label
        self.error_label = QLabel("")
        self.error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error_label.setStyleSheet("color: red; font-size: 12px; font-family: 'Segoe UI';")
        self.error_label.hide()
        form_layout.addWidget(self.error_label)

        layout.addWidget(form_card)

        # State
        self.role = None
        self.user_code = None
        self.selected_driver_row = None
        self.selected_collection_row = None
        self.selected_driver_code = None

    # ✅ Handle login
    def handle_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if username == "admin" and password == "hazmat":
            self.dashboard = DashboardWindow(role="admin", user_code="ADM001")
            self.dashboard.showMaximized()
            self.accept()  # ✅ closes dialog cleanly
        else:
            self.error_label.setText("❌ Invalid login. Please try again.")
            self.error_label.show()

    def handle_login(self):
        users = {
            "hendrik": {"password": "hendrik", "role": "user", "code": "HK"},
            "morne": {"password": "morne", "role": "user", "code": "MV"},
            "justin": {"password": "justin", "role": "user", "code": "JB"},
            "admin": {"password": "admin", "role": "admin", "code": "ALL"}
        }

        username = self.username_input.text().lower()
        password = self.password_input.text()

        if username in users and users[username]["password"] == password:
            self.role = users[username]["role"]
            self.user_code = users[username]["code"]
            self.accept()
            self.close()
        else:
            self.username_input.setText("")
            self.password_input.setText("")
            self.username_input.setPlaceholderText("Invalid credentials")

class DashboardWindow(QMainWindow):
        def __init__(self, role, user_code):
            super().__init__()
            self.setStyleSheet("""
                        QMainWindow {
        background-color: #F1F8E9;
    }
    QLabel {
        color: #333333;
        font-size: 14px;
        font-family: 'Segoe UI';
    }
    QPushButton {
        background-color: #2E7D32;
        color: white;
        padding: 6px;
        border-radius: 4px;
        font-family: 'Segoe UI';
    }
    QPushButton:hover {
        background-color: #388E3C;
    }
    QLineEdit, QTextEdit {
        background-color: #ffffff;
        color: #333333;
        border: 1px solid #C8E6C9;
        padding: 4px;
        font-family: 'Segoe UI';
    }
    QTabWidget::pane {
        border: 1px solid #C8E6C9;
    }
    QTabBar::tab {
        background: #ffffff;
        color: #2E7D32;
        padding: 8px;
        font-family: 'Segoe UI';
    }
    QTabBar::tab:selected {
        background: #2E7D32;
        color: white;

                    """)
            self.setWindowTitle("Hazmat Global Dashboard")
            self.role = role
            self.user_code = user_code
            self.init_ui()
            self.showMaximized()

        def update_unassigned_table(self, data: list):
            unassigned = [
                item for item in data
                if (not item.get("driver") or item["driver"] == "Unassigned")
                   and item.get("status") != "Delivered"
            ]

            self.unassigned_table.setRowCount(len(unassigned))
            for i, item in enumerate(unassigned):
                self.unassigned_table.setItem(i, 0, QTableWidgetItem(item.get("hazjnb_ref", "—")))
                self.unassigned_table.setItem(i, 1, QTableWidgetItem(item.get("company", "—")))
                self.unassigned_table.setItem(i, 2, QTableWidgetItem(item.get("pickup_date", "—")))
                self.unassigned_table.setItem(i, 3, QTableWidgetItem(item.get("address", "—")))


        def update_completed_table(self, data: list):
            self.completed_table.setRowCount(len(data))
            for i, item in enumerate(data):
                self.completed_table.setItem(i, 0, QTableWidgetItem(item.get("ops", "—")))
                self.completed_table.setItem(i, 1, QTableWidgetItem(item.get("company", "—")))
                self.completed_table.setItem(i, 2, QTableWidgetItem(item.get("delivery_date", "—")))
                self.completed_table.setItem(i, 3, QTableWidgetItem(item.get("signed_by", "—")))
                self.completed_table.setItem(i, 4, QTableWidgetItem(item.get("document", "—")))
                self.completed_table.setItem(i, 5, QTableWidgetItem(item.get("pod", "—")))
                self.completed_table.setItem(i, 6, QTableWidgetItem(item.get("time", "—")))

        def select_driver(self, row, column):
            if self.selected_driver_row == row:
                self.driver_table.clearSelection()
                self.selected_driver_row = None
                self.selected_driver_code = None
            else:
                self.driver_table.selectRow(row)
                self.selected_driver_row = row
                self.selected_driver_code = self.driver_table.item(row, 1).text()
            self.update_selection_label()

        def select_collection(self, row, column):
            item = self.unassigned_table.item(row, 3)
            if item is None:
                self.selection_label.setText("⚠️ No address available")
                return

            address = item.text().strip()
            if not address:
                self.selection_label.setText("⚠️ Invalid collection selected")
                return

            if self.selected_collection_row == row:
                self.unassigned_table.clearSelection()
                self.selected_collection_row = None
                # Reset map
                self.driver_map.page().runJavaScript("initMap();")
            else:
                self.unassigned_table.selectRow(row)
                self.selected_collection_row = row

                # Drop a pin directly into the embedded map
                encoded = address.replace(" ", "+")
                js = f"""
                var geocoder = new google.maps.Geocoder();
                geocoder.geocode({{ 'address': '{encoded}' }}, function(results, status) {{
                    if (status === 'OK') {{
                        new google.maps.Marker({{
                            map: map,
                            position: results[0].geometry.location,
                            icon: "http://maps.google.com/mapfiles/ms/icons/blue-dot.png",
                            title: "{address}"
                        }});
                        map.setCenter(results[0].geometry.location);
                    }}
                }});
                """
                self.driver_map.page().runJavaScript(js)

            self.update_selection_label()

        def update_selection_label(self):
            driver = "None"
            company = "None"

            if self.selected_driver_row is not None:
                item = self.driver_table.item(self.selected_driver_row, 0)
                if item:
                    driver = item.text()

            if self.selected_collection_row is not None:
                item = self.unassigned_table.item(self.selected_collection_row, 1)
                if item:
                    company = item.text()

            self.selection_label.setText(f"Selected: {driver} → {company}")

        def assign_driver_to_collection(self):
            if self.selected_driver_row is None or self.selected_collection_row is None:
                self.selection_label.setText("⚠️ Please select both a driver and a collection")
                return

            # Safely get haz_ref
            haz_item = self.unassigned_table.item(self.selected_collection_row, 0)
            if haz_item is None or not haz_item.text().strip():
                self.selection_label.setText("⚠️ No valid HAZ Ref for this collection")
                return
            haz_ref = haz_item.text().strip()

            driver_code = self.selected_driver_code
            if not driver_code:
                self.selection_label.setText("⚠️ No driver code selected")
                return

            # 🔁 Send update to backend
            try:
                r = requests.post("https://hazmat-collection.onrender.com/assign", json={
                    "driver_code": driver_code,
                    "hazjnb_ref": haz_ref
                }, timeout=5)
                if r.status_code == 200:
                    self.selection_label.setText(f"✅ Assigned {driver_code} → {haz_ref}")
                else:
                    self.selection_label.setText(f"⚠️ Backend error: {r.status_code}")
            except Exception as e:
                self.selection_label.setText(f"❌ Failed to push assignment: {e}")
                return

            # ✅ Reset selections
            self.driver_table.clearSelection()
            self.unassigned_table.clearSelection()
            self.selected_driver_row = None
            self.selected_collection_row = None
            self.selected_driver_code = None

            # Reset map safely
            if hasattr(self, "driver_map"):
                self.driver_map.page().runJavaScript("initMap();")

            # 🔄 Refresh table
            self.poller.fetch_collections()

        def build_logo_header(self):
                logo = QLabel()
                pixmap = QPixmap("static/logo.png")
                logo.setPixmap(pixmap.scaledToHeight(60))
                logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
                return logo

        def init_ui(self):
            self.tabs = QTabWidget()
            self.tabs.addTab(self.build_map_tab(), "Map")
            self.tabs.addTab(self.build_driver_tab(), "Select Driver")
            self.tabs.addTab(self.build_collections_tab(), "Collections")
            self.tabs.addTab(self.build_updates_tab(), "Client Updates")
            self.tabs.addTab(self.build_completed_tab(), "Completed Shipments")
            self.setCentralWidget(self.tabs)
            self.tabs.currentChanged.connect(self.reset_driver_tab_selection)
            self.poller = TablePoller()
            self.poller.collections_updated.connect(self.update_unassigned_table)
            self.poller.assigned_updated.connect(self.refresh_collections_tab)
            self.poller.completed_updated.connect(self.refresh_completed_tab)

        def reset_driver_tab_selection(self, index):
            if self.tabs.tabText(index) == "Select Driver":
                self.driver_table.clearSelection()
                self.unassigned_table.clearSelection()
                self.selected_driver_row = None
                self.selected_collection_row = None
                self.selected_driver_code = None
                self.selection_label.setText("No selection made")

        def refresh_collections_tab(self, data: list):
            assigned = [item for item in data if
                        item.get("driver") and item["driver"] != "Unassigned"]

            self.collections_table.setRowCount(len(assigned))
            for i, item in enumerate(assigned):
                self.collections_table.setItem(i, 0, QTableWidgetItem("—"))  # HMJ Ref placeholder
                self.collections_table.setItem(i, 1, QTableWidgetItem(item.get("hazjnb_ref", "—")))
                self.collections_table.setItem(i, 2, QTableWidgetItem(item.get("company", "—")))
                self.collections_table.setItem(i, 3, QTableWidgetItem(item.get("pickup_date", "—")))
                self.collections_table.setItem(i, 4, QTableWidgetItem(item.get("driver", "—")))
                self.collections_table.setItem(i, 5, QTableWidgetItem(item.get("status", "Assigned")))

        def refresh_updates_tab(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/updates")
                if response.status_code == 200:
                    updates = response.json()
                    self.update_table.setRowCount(len(updates))
                    for i, u in enumerate(updates):
                        if self.role == "admin" or u["ops"] == self.user_code:
                            self.update_table.setItem(i, 0, QTableWidgetItem(u["ops"]))
                            self.update_table.setItem(i, 1, QTableWidgetItem(u["hmj"]))
                            self.update_table.setItem(i, 2, QTableWidgetItem(u["haz"]))
                            self.update_table.setItem(i, 3, QTableWidgetItem(u["company"]))
                            self.update_table.setItem(i, 4, QTableWidgetItem(u["date"]))
                            self.update_table.setItem(i, 5, QTableWidgetItem(u["time"]))
                            update_item = QTableWidgetItem(u["update"])
                            update_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                            self.update_table.setItem(i, 6, update_item)
            except Exception as e:
                print("❌ Failed to refresh updates:", e)

        def refresh_completed_tab(self, completed: list):
            self.completed_table.setRowCount(len(completed))
            for i, c in enumerate(completed):
                self.completed_table.setItem(i, 0, QTableWidgetItem(c["ops"]))
                self.completed_table.setItem(i, 1, QTableWidgetItem(c["company"]))
                self.completed_table.setItem(i, 2, QTableWidgetItem(c["delivery_date"]))
                self.completed_table.setItem(i, 3, QTableWidgetItem(c["time"]))
                self.completed_table.setItem(i, 4, QTableWidgetItem(c["signed_by"]))
                self.completed_table.setItem(i, 5, QTableWidgetItem(c["document"]))
                self.completed_table.setItem(i, 6, QTableWidgetItem(c["pod"]))

        def build_map_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            # Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setContentsMargins(0, 4, 0, 4)
            logo.setFixedHeight(70)
            layout.addWidget(logo)

            # Google Map via embedded HTML
            map_view = QWebEngineView()

            html = f"""
            <!DOCTYPE html>
            <html>
              <head>
                <style>html, body, #map {{ height:100%; margin:0; padding:0; }}</style>
                <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyCqimNSU2P32FU4be5Us4W87GLuliezU-8"></script>
                <script>
                  let map;
                  let driverMarkers = {{}};

                  function initMap() {{
                    map = new google.maps.Map(document.getElementById("map"), {{
                      center: {{ lat: -26.2041, lng: 28.0473 }},
                      zoom: 10
                    }});
                  }}

                  function updateDriver(id, lat, lng) {{
                    if (driverMarkers[id]) {{
                      driverMarkers[id].setPosition({{ lat: lat, lng: lng }});
                    }} else {{
                      driverMarkers[id] = new google.maps.Marker({{
                        position: {{ lat: lat, lng: lng }},
                        map: map,
                        title: id,
                        icon: "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
                      }});
                    }}
                  }}
                </script>
              </head>
              <body onload="initMap()">
                <div id="map"></div>
              </body>
            </html>
            """

            map_view.setHtml(html)
            map_view.setMinimumHeight(500)
            layout.addWidget(map_view)

            # Save reference so we can update pins later
            self.map_view = map_view

            return tab

        from PyQt6.QtWebEngineWidgets import QWebEngineView

        def build_driver_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(20, 10, 20, 10)
            layout.setSpacing(10)

            # 🔰 Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setContentsMargins(0, 4, 0, 4)
            logo.setFixedHeight(70)
            layout.addWidget(logo)

            # 🔀 Splitter: Top (tables) vs Bottom (map + controls)
            splitter = QSplitter(Qt.Orientation.Vertical)
            splitter.setHandleWidth(2)

            # 🔼 Top Widget: Driver + Collection Tables
            top_widget = QWidget()
            top_layout = QHBoxLayout(top_widget)
            top_layout.setContentsMargins(0, 0, 0, 0)
            top_layout.setSpacing(20)

            # 👤 Driver Table
            self.driver_table = QTableWidget()
            self.driver_table.setColumnCount(2)
            self.driver_table.setHorizontalHeaderLabels(["Driver", "Code"])
            self.driver_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.driver_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.driver_table.setStyleSheet("""
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-family: 'Segoe UI';
                    font-size: 14px;
                    gridline-color: #C8E6C9;
                }
                QHeaderView::section {
                    background-color: #2E7D32;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                    font-family: 'Segoe UI';
                }
                QTableWidget::item:selected {
                    background-color: #388E3C;
                    color: #ffffff;
                }
            """)
            self.driver_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
            self.driver_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            self.driver_table.cellClicked.connect(self.select_driver)
            top_layout.addWidget(self.driver_table)
            # Example driver list (replace with real data or API call)
            drivers = [
                {"name": "Ntivulo Khosa", "code": "NK"},
                {"name": "Kenneth Rangata", "code": "KR"},
                {"name": "Vusi Nyalungu", "code": "VN"},
            ]

            self.driver_table.setRowCount(len(drivers))
            for i, d in enumerate(drivers):
                self.driver_table.setItem(i, 0, QTableWidgetItem(d["name"]))
                self.driver_table.setItem(i, 1, QTableWidgetItem(d["code"]))

            # 📦 Collection Table
            self.unassigned_table = QTableWidget()
            self.unassigned_table.setColumnCount(4)
            self.unassigned_table.setHorizontalHeaderLabels(["HAZ Ref#", "Company", "Pickup Date", "Address"])
            self.unassigned_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.unassigned_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self.unassigned_table.setStyleSheet("""
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-family: 'Segoe UI';
                    font-size: 14px;
                    gridline-color: #C8E6C9;
                }
                QHeaderView::section {
                    background-color: #2E7D32;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                    font-family: 'Segoe UI';
                }
                QTableWidget::item:selected {
                    background-color: #388E3C;
                    color: #ffffff;
                }
            """)
            for i in range(4):
                self.unassigned_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            self.unassigned_table.cellClicked.connect(self.select_collection)
            top_layout.addWidget(self.unassigned_table)

            splitter.addWidget(top_widget)

            # 🔻 Bottom Widget: Selection + Assign + Map
            bottom_widget = QWidget()
            bottom_layout = QVBoxLayout(bottom_widget)
            bottom_layout.setContentsMargins(0, 0, 0, 0)
            bottom_layout.setSpacing(10)

            # 🧭 Selection Label
            self.selection_label = QLabel("No selection made")
            self.selection_label.setStyleSheet("color: #333333; font-size: 14px; font-family: 'Segoe UI';")
            bottom_layout.addWidget(self.selection_label)

            # ✅ Assign Button
            self.assign_btn = QPushButton("Assign Driver to Collection")
            self.assign_btn.setFixedHeight(36)
            self.assign_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2E7D32;
                    color: white;
                    font-weight: bold;
                    border-radius: 6px;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                }
                QPushButton:hover {
                    background-color: #388E3C;
                }
            """)
            self.assign_btn.clicked.connect(self.assign_driver_to_collection)
            bottom_layout.addWidget(self.assign_btn)

            # 🗺️ Embedded Google Map
            self.driver_map = QWebEngineView()
            html = f"""
            <!DOCTYPE html>
            <html>
              <head>
                <style>html, body, #map {{ height:100%; margin:0; padding:0; }}</style>
                <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyCqimNSU2P32FU4be5Us4W87GLuliezU-8"></script>
                <script>
                  let map;
                  let driverMarkers = {{}};
                  function initMap() {{
                    map = new google.maps.Map(document.getElementById("map"), {{
                      center: {{ lat: -26.2041, lng: 28.0473 }},
                      zoom: 10
                    }});
                  }}
                  function updateDriver(id, lat, lng) {{
                    if (driverMarkers[id]) {{
                      driverMarkers[id].setPosition({{ lat: lat, lng: lng }});
                    }} else {{
                      driverMarkers[id] = new google.maps.Marker({{
                        position: {{ lat: lat, lng: lng }},
                        map: map,
                        title: id,
                        icon: "http://maps.google.com/mapfiles/ms/icons/red-dot.png"
                      }});
                    }}
                  }}
                </script>
              </head>
              <body onload="initMap()">
                <div id="map"></div>
              </body>
            </html>
            """
            self.driver_map.setHtml(html)
            self.driver_map.setMinimumHeight(400)
            bottom_layout.addWidget(self.driver_map)

            splitter.addWidget(bottom_widget)
            splitter.setStretchFactor(1, 1)

            layout.addWidget(splitter)
            return tab

        def build_collections_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaled(200, 40, Qt.AspectRatioMode.KeepAspectRatio))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)

            title = QLabel("📦 Active Collections")
            title.setStyleSheet("color: #f2f2f2; font-size: 18px; font-weight: bold;")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            self.collections_table = QTableWidget()
            self.collections_table.setColumnCount(5)
            self.collections_table.setHorizontalHeaderLabels([
                "HAZ Ref#", "Company", "Pickup Date", "Driver", "Status"
            ])
            self.collections_table.verticalHeader().setDefaultSectionSize(40)
            self.collections_table.horizontalHeader().setStretchLastSection(True)
            self.collections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.collections_table.setStyleSheet("""
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-size: 14px;
                    gridline-color: #C8E6C9;
                    font-family: 'Segoe UI';
                }
                QHeaderView::section {
                    background-color: #2E7D32;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                    font-family: 'Segoe UI';
                }
            """)


            table_container = QWidget()
            table_layout = QVBoxLayout(table_container)
            table_layout.setContentsMargins(20, 10, 20, 10)
            table_layout.addWidget(self.collections_table)
            layout.addWidget(table_container)

            return tab

        def build_updates_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(20, 10, 20, 10)
            layout.setSpacing(20)

            # 🔰 Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaledToHeight(60, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setContentsMargins(0, 4, 0, 4)
            logo.setFixedHeight(70)
            layout.addWidget(logo)

            # 📝 Form Card
            form_card = QWidget()
            form_card.setStyleSheet("""
                QWidget {
                    background-color: #F1F8E9;
                    border: 1px solid #C8E6C9;
                    border-radius: 8px;
                }
            """)
            form_layout = QGridLayout(form_card)
            form_layout.setContentsMargins(20, 20, 20, 20)
            form_layout.setHorizontalSpacing(15)
            form_layout.setVerticalSpacing(10)

            input_style = """
                QLineEdit, QTextEdit {
                    background-color: #ffffff;
                    border: 1px solid #C8E6C9;
                    border-radius: 4px;
                    padding: 6px;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                    color: #333333;
                }
            """

            # Fields
            self.input_hmj = QLineEdit()
            self.input_hmj.setPlaceholderText("HMJ Ref#")
            self.input_hmj.setStyleSheet(input_style)

            self.input_haz = QLineEdit()
            self.input_haz.setPlaceholderText("HAZ Ref#")
            self.input_haz.setStyleSheet(input_style)

            self.input_company = QLineEdit()
            self.input_company.setPlaceholderText("Company")
            self.input_company.setStyleSheet(input_style)

            self.input_update = QTextEdit()
            self.input_update.setPlaceholderText("Latest Update")
            self.input_update.setFixedHeight(60)
            self.input_update.setStyleSheet(input_style)

            submit_btn = QPushButton("Submit Update")
            submit_btn.setFixedHeight(36)
            submit_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2E7D32;
                    color: white;
                    font-weight: bold;
                    border-radius: 6px;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                }
                QPushButton:hover {
                    background-color: #388E3C;
                }
            """)
            submit_btn.clicked.connect(self.submit_update)

            # Grid layout
            form_layout.addWidget(QLabel("HMJ Ref#"), 0, 0)
            form_layout.addWidget(self.input_hmj, 0, 1)
            form_layout.addWidget(QLabel("HAZ Ref#"), 0, 2)
            form_layout.addWidget(self.input_haz, 0, 3)

            form_layout.addWidget(QLabel("Company"), 1, 0)
            form_layout.addWidget(self.input_company, 1, 1, 1, 3)

            form_layout.addWidget(QLabel("Latest Update"), 2, 0)
            form_layout.addWidget(self.input_update, 2, 1, 1, 3)

            form_layout.addWidget(submit_btn, 3, 3)

            layout.addWidget(form_card)

            # 🔍 Search Bar
            search_layout = QHBoxLayout()
            search_label = QLabel("Search HMJ Ref#:")
            search_label.setStyleSheet("color: #2E7D32; font-weight: bold; font-size: 14px; font-family: 'Segoe UI';")

            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("Enter HMJ Ref#")
            self.search_input.setStyleSheet(input_style)
            self.search_input.textChanged.connect(self.filter_updates)

            search_layout.addWidget(search_label)
            search_layout.addWidget(self.search_input)
            layout.addLayout(search_layout)

            # 📋 Update Table
            self.update_table = QTableWidget()
            self.update_table.setColumnCount(7)
            self.update_table.setHorizontalHeaderLabels([
                "Ops", "HMJ Ref#", "HAZ Ref#", "Company", "Date", "Time", "Latest Update"
            ])
            self.update_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.update_table.setStyleSheet("""
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-size: 14px;
                    gridline-color: #C8E6C9;
                    font-family: 'Segoe UI';
                }
                QHeaderView::section {
                    background-color: #2E7D32;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                    font-family: 'Segoe UI';
                }
            """)
            self.update_table.cellClicked.connect(self.handle_update_row_click)
            layout.addWidget(self.update_table)

            self.load_updates()
            return tab

        def filter_updates(self):
            """
            Filters the update_table rows based on the HMJ Ref# entered in the search bar.
            """
            query = self.search_input.text().strip().lower()
            for row in range(self.update_table.rowCount()):
                item = self.update_table.item(row, 1)  # HMJ Ref# column
                if item and query in item.text().lower():
                    self.update_table.setRowHidden(row, False)
                else:
                    self.update_table.setRowHidden(row, True)

        def handle_update_row_click(self, row, column):
            """
            Auto-fills the form fields when a row is clicked in the update_table.
            """
            hmj_item = self.update_table.item(row, 1)
            haz_item = self.update_table.item(row, 2)
            company_item = self.update_table.item(row, 3)
            update_item = self.update_table.item(row, 6)

            if hmj_item:
                self.input_hmj.setText(hmj_item.text())
            if haz_item:
                self.input_haz.setText(haz_item.text())
            if company_item:
                self.input_company.setText(company_item.text())
            if update_item:
                self.input_update.setPlainText(update_item.text())

        def build_completed_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(20, 10, 20, 10)
            layout.setSpacing(10)

            # Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)

            # Table
            self.completed_table = QTableWidget()
            self.completed_table.setColumnCount(8)
            self.completed_table.setHorizontalHeaderLabels([
                "Ops", "Client", "Delivery Date", "Time", "Signed By", "Document", "POD", "Invoice#"
            ])
            self.completed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.completed_table.setStyleSheet("""
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-size: 14px;
                    gridline-color: #C8E6C9;
                    font-family: 'Segoe UI';
                }
                QHeaderView::section {
                    background-color: #2E7D32;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                    font-family: 'Segoe UI';
                }
                }
            """)
            self.completed_table.cellClicked.connect(self.handle_completed_click)
            layout.addWidget(self.completed_table)

            return tab

        def submit_update(self):
            from datetime import datetime
            now = datetime.now()
            date = now.strftime("%Y-%m-%d")
            time = now.strftime("%H:%M")

            row = self.update_table.rowCount()
            self.update_table.insertRow(row)
            self.update_table.setItem(row, 0, QTableWidgetItem(self.user_code))
            self.update_table.setItem(row, 1, QTableWidgetItem(self.input_hmj.text()))
            self.update_table.setItem(row, 2, QTableWidgetItem(self.input_haz.text()))
            self.update_table.setItem(row, 3, QTableWidgetItem(self.input_company.text()))
            self.update_table.setItem(row, 4, QTableWidgetItem(date))
            self.update_table.setItem(row, 5, QTableWidgetItem(time))

            update_item = QTableWidgetItem(self.input_update.toPlainText())
            update_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            self.update_table.setItem(row, 6, update_item)

            self.input_hmj.clear()
            self.input_haz.clear()
            self.input_company.clear()
            self.input_update.clear()

        def load_updates(self):
            sample=[]
            for u in sample:
                if self.role == "admin" or u["ops"] == self.user_code:
                    row = self.update_table.rowCount()
                    self.update_table.insertRow(row)
                    for i, key in enumerate(["ops", "hmj", "haz", "company", "date", "time"]):
                        self.update_table.setItem(row, i, QTableWidgetItem(u[key]))
                    update_item = QTableWidgetItem(u["update"])
                    update_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                    self.update_table.setItem(row, 6, update_item)

        def handle_cell_click(self, row, column):
            if column == 1:
                dialog = QDialog(self)
                dialog.setWindowTitle("Update Shipment")
                layout = QVBoxLayout(dialog)

                update_field = QTextEdit()
                update_field.setText(self.update_table.item(row, 6).text())
                layout.addWidget(QLabel("Edit Update:"))
                layout.addWidget(update_field)

                date_field = QDateEdit()
                date_field.setCalendarPopup(True)
                date_field.setDate(QDate.currentDate())
                layout.addWidget(QLabel("Delivery Date:"))
                layout.addWidget(date_field)

                time_field = QLineEdit()
                time_field.setPlaceholderText("Delivery Time (e.g. 14:30)")
                layout.addWidget(QLabel("Delivery Time:"))
                layout.addWidget(time_field)

                signed_by_field = QLineEdit()
                signed_by_field.setPlaceholderText("Signed By")
                layout.addWidget(QLabel("Signed By:"))
                layout.addWidget(signed_by_field)

                save_btn = QPushButton("Save Update")
                close_btn = QPushButton("Close File")
                layout.addWidget(save_btn)
                layout.addWidget(close_btn)

                def save():
                    new_text = update_field.toPlainText()
                    update_item = QTableWidgetItem(new_text)
                    update_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                    update_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    self.update_table.setItem(row, 6, update_item)

                    from datetime import datetime
                    now = datetime.now()
                    self.update_table.setItem(row, 4, QTableWidgetItem(now.strftime("%Y-%m-%d")))
                    self.update_table.setItem(row, 5, QTableWidgetItem(now.strftime("%H:%M")))
                    dialog.accept()

                def close_file():
                    doc_path, _ = QFileDialog.getOpenFileName(self, "Upload Shipment Document")
                    pod_path, _ = QFileDialog.getOpenFileName(self, "Upload Proof of Delivery")

                    if doc_path and pod_path:
                        ops = self.update_table.item(row, 0).text()
                        company = self.update_table.item(row, 3).text()
                        delivery_date = date_field.date().toString("yyyy-MM-dd")
                        delivery_time = time_field.text()
                        signed_by = signed_by_field.text()

                        new_row = self.completed_table.rowCount()
                        self.completed_table.insertRow(new_row)
                        self.completed_table.setItem(new_row, 0, QTableWidgetItem(ops))
                        self.completed_table.setItem(new_row, 1, QTableWidgetItem(company))
                        self.completed_table.setItem(new_row, 2, QTableWidgetItem(delivery_date))
                        self.completed_table.setItem(new_row, 3, QTableWidgetItem(delivery_time))
                        self.completed_table.setItem(new_row, 4, QTableWidgetItem(signed_by))
                        self.completed_table.setItem(new_row, 5, QTableWidgetItem(doc_path))
                        self.completed_table.setItem(new_row, 6, QTableWidgetItem(pod_path))

                        self.update_table.removeRow(row)
                        dialog.accept()

                save_btn.clicked.connect(save)
                close_btn.clicked.connect(close_file)
                dialog.exec()

        def handle_completed_click(self, row, column):
            if column in [5, 6]:  # Document or POD
                path = self.completed_table.item(row, column).text()
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))


if __name__ == "__main__":
    app = QApplication(sys.argv)
    login = LoginDialog()
    if login.exec():
        window = DashboardWindow(role=login.role, user_code=login.user_code)
        window.show()
        sys.exit(app.exec())
