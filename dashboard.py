import sys
import threading
import requests
from dotenv import load_dotenv
import sqlite3
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QDialog,
    QTabWidget, QLineEdit, QTextEdit, QSizePolicy, QScrollArea,
    QHeaderView, QFileDialog, QDateEdit, QGridLayout, QSplitter
)
from PyQt6.QtCore import (
    QObject, QTimer, pyqtSignal, Qt, QDate, QUrl, QPoint
)
from PyQt6.QtGui import (
    QDesktopServices, QPixmap, QPalette, QColor
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QRect
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QObject, QTimer, pyqtSignal, QUrl, QByteArray
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import json
load_dotenv()
class TablePoller(QObject):
    collections_updated = pyqtSignal(list)
    assigned_updated = pyqtSignal(list)
    completed_updated = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.nam = QNetworkAccessManager(self)

        # Non-blocking poll every 5s (adjust as needed)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_all)
        self.timer.start(5000)

        # Track replies to prevent premature GC
        self._pending = set()

    def poll_all(self):
        self._get_json("https://hazmat-collection.onrender.com/ops/collections", self._on_collections)
        self._get_json("https://hazmat-collection.onrender.com/ops/assigned", self._on_assigned)
        self._get_json("https://hazmat-collection.onrender.com/ops/completed", self._on_completed)

    def _get_json(self, url: str, callback):
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"Accept", b"application/json, */*")
        reply = self.nam.get(req)
        self._pending.add(reply)

        def finish():
            try:
                if reply.error() == QNetworkReply.NetworkError.NoError:
                    data_bytes: QByteArray = reply.readAll()
                    text = bytes(data_bytes).decode("utf-8", errors="replace")

                    ct = reply.header(QNetworkRequest.KnownHeaders.ContentTypeHeader)
                    if ct and "application/json" in str(ct).lower():
                        try:
                            payload = json.loads(text)
                            callback(payload)
                        except json.JSONDecodeError as e:
                            print(f"❌ {url} JSON decode failed:", e)
                            print("Raw response:", text[:200])
                    else:
                        # Endpoint returned HTML or other content; skip
                        print(f"⚠️ {url} returned non-JSON content-type:", ct)
                else:
                    print(f"⚠️ {url} network error:", reply.error(), reply.errorString())
            finally:
                self._pending.discard(reply)
                reply.deleteLater()

        reply.finished.connect(finish)

    # Emit results via queued signals (GUI-safe)
    def _on_collections(self, payload: list):
        self.collections_updated.emit(payload)

    def _on_assigned(self, payload: list):
        self.assigned_updated.emit(payload)

    def _on_completed(self, payload: list):
        self.completed_updated.emit(payload)

    def select_driver(self, row, column):
        return

    def select_collection(self, row, column):
        return

    def update_selection_label(self):
        return

    def assign_driver_to_collection(self):
        return

    def reset_driver_tab_selection(self, index):
        # No-op since "Select Driver" tab is gone
        return
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


class Toast(QWidget):
    def __init__(self, parent, message, x, y, duration=6000):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.ToolTip)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("""
            QLabel {
                background-color: rgba(46, 125, 50, 220);
                color: white;
                padding: 8px 16px;
                border-radius: 6px;
                font-family: 'Segoe UI';
                font-size: 13px;
            }
        """)

        self.label = QLabel(message, self)
        self.label.adjustSize()
        self.resize(self.label.sizeHint())

        # Position inside parent window
        self.move(parent.mapToGlobal(QPoint(x, y + 50)))  # start below
        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(400)
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(parent.mapToGlobal(QPoint(x, y)))
        self.anim.start()

        QTimer.singleShot(duration, self.close)

class ToastManager:
    def __init__(self, parent):
        self.parent = parent
        self.toasts = []

    def show_toast(self, message):
        # Calculate position based on current stack
        base_x = self.parent.rect().width() - 220  # fixed width offset
        base_y = self.parent.rect().height() - 80
        offset = len(self.toasts) * 60  # vertical spacing between toasts

        # Create toast
        toast = Toast(self.parent, message, base_x, base_y - offset)
        toast.show()
        self.toasts.append(toast)

        # Remove when closed
        toast.destroyed.connect(lambda: self._remove_toast(toast))

    def _remove_toast(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            # Shift remaining toasts down
            for i, t in enumerate(self.toasts):
                new_y = self.parent.mapToGlobal(QPoint(
                    self.parent.rect().width() - 220,
                    self.parent.rect().height() - 80 - i * 60
                ))
                anim = QPropertyAnimation(t, b"pos")
                anim.setDuration(300)
                anim.setEndValue(new_y)
                anim.start()


class DashboardWindow(QMainWindow):
        def __init__(self, role, user_code):
            super().__init__()
            self.toast_manager = ToastManager(self)
            self.setStyleSheet("""
                /* === Main Window === */
                QMainWindow {
                    background-color: #F1F8E9; /* same as website background */
                }

                /* === Tabs === */
                QTabWidget::pane {
                    border: 1px solid #C8E6C9;
                    border-radius: 6px;
                    background: #ffffff;
                    margin-top: -1px;
                }

                QTabBar::tab {
                    background: #ffffff;
                    color: #2E7D32;
                    padding: 10px 18px;
                    font-family: 'Segoe UI';
                    font-size: 14px;
                    border: 1px solid #C8E6C9;
                    border-bottom: none;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    margin-right: 2px;
                }

                QTabBar::tab:hover {
                    background: #F1F8E9; /* subtle website tint */
                    color: #1B5E20;
                }

                QTabBar::tab:selected {
                    background: #2E7D32;   /* Hazmat green */
                    color: #ffffff;
                    font-weight: bold;
                    border: 1px solid #2E7D32;
                    border-bottom: none;
                }

                /* === Labels === */
                QLabel {
                    color: #333333;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                }

                /* === Buttons === */
                QPushButton {
                    background-color: #2E7D32;
                    color: #ffffff;
                    padding: 8px 14px;
                    border-radius: 6px;
                    font-family: 'Segoe UI';
                    font-size: 14px;
                    font-weight: 500;
                    border: none;
                }

                QPushButton:hover {
                    background-color: #388E3C;
                }

                QPushButton:pressed {
                    background-color: #1B5E20;
                }

                /* === Inputs === */
                QLineEdit, QTextEdit {
                    background-color: #ffffff;
                    color: #333333;
                    border: 1px solid #C8E6C9;
                    border-radius: 4px;
                    padding: 6px 10px;
                    font-family: 'Segoe UI';
                    font-size: 14px;
                }

                QLineEdit:focus, QTextEdit:focus {
                    border: 1px solid #2E7D32;
                    box-shadow: 0 0 4px rgba(46, 125, 50, 0.4);
                }

                /* === Tables === */
                QTableWidget {
                    background-color: #ffffff;
                    color: #333333;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                    gridline-color: #C8E6C9;
                    border: 1px solid #C8E6C9;
                    border-radius: 6px;
                }

                QHeaderView::section {
                    background-color: #2E7D32;
                    color: #ffffff;
                    font-size: 14px;
                    font-weight: 600;
                    padding: 6px;
                    font-family: 'Segoe UI';
                    border: none;
                }

                QTableWidget::item:selected {
                    background-color: #C8E6C9;
                    color: #1B5E20;
                }
            """)
            self.setWindowTitle("Hazmat Global Dashboard")
            self.role = role
            self.user_code = user_code
            self.init_ui()
            self.showMaximized()

        def update_unassigned_table(self, data: list):
            if not hasattr(self, "unassigned_table"):
                return

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

        def build_logo_header(self, height: int = 60):
            container = QWidget()
            container.setFixedHeight(height + 16)  # ✅ Enough room for logo + padding

            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            logo.setContentsMargins(0, 4, 0, 4)
            logo.setFixedHeight(height + 4)  # ✅ Prevent clipping

            layout.addWidget(logo)

            container.setStyleSheet("""
                background-color: #F1F8E9;
                border-bottom: 1px solid #C8E6C9;
            """)

            return container

        def init_ui(self):
            self.tabs = QTabWidget()
            self.tabs.addTab(self.build_map_tab(), "Map")
            self.tabs.addTab(self.build_deliveries_tab(), "Deliveries")
            self.tabs.addTab(self.build_collections_tab(), "Collections")
            self.tabs.addTab(self.build_updates_tab(), "Client Updates")
            self.tabs.addTab(self.build_completed_tab(), "Completed Shipments")
            self.setCentralWidget(self.tabs)

            self.poller = TablePoller()
            self.poller.collections_updated.connect(self.update_unassigned_table,
                                                    type=Qt.ConnectionType.QueuedConnection)
            self.poller.assigned_updated.connect(self.refresh_collections_tab, type=Qt.ConnectionType.QueuedConnection)
            self.poller.completed_updated.connect(self.refresh_completed_tab, type=Qt.ConnectionType.QueuedConnection)

        def refresh_collections_tab(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/collections")
                if response.status_code == 200:
                    data = response.json()
                    assigned = [item for item in data if item.get("driver") and item["driver"] != "Unassigned"]

                    self.collections_table.setRowCount(len(assigned))
                    for i, item in enumerate(assigned):
                        self.collections_table.setItem(i, 0, QTableWidgetItem(item.get("hmj", "—")))
                        self.collections_table.setItem(i, 1, QTableWidgetItem(item.get("hazjnb_ref", "—")))
                        self.collections_table.setItem(i, 2, QTableWidgetItem(item.get("company", "—")))
                        self.collections_table.setItem(i, 3, QTableWidgetItem(item.get("pickup_date", "—")))
                        self.collections_table.setItem(i, 4, QTableWidgetItem(item.get("driver", "—")))
                        self.collections_table.setItem(i, 5, QTableWidgetItem(item.get("status", "Assigned")))
            except Exception as e:
                print("❌ Failed to refresh collections:", e)

        def refresh_deliveries_tab(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/assigned")
                if response.status_code == 200:
                    deliveries = response.json()
                    self.deliveries_table.setRowCount(len(deliveries))
                    for i, item in enumerate(deliveries):
                        self.deliveries_table.setItem(i, 0, QTableWidgetItem(item.get("hazjnb_ref", "—")))
                        self.deliveries_table.setItem(i, 1, QTableWidgetItem(item.get("company", "—")))
                        self.deliveries_table.setItem(i, 2, QTableWidgetItem(item.get("pickup_date", "—")))
                        self.deliveries_table.setItem(i, 3, QTableWidgetItem(item.get("driver", "—")))
                        self.deliveries_table.setItem(i, 4, QTableWidgetItem(item.get("status", "—")))
            except Exception as e:
                print("❌ Failed to refresh deliveries:", e)

        def refresh_updates_tab(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/updates")
                if response.status_code == 200:
                    updates = response.json()
                    self.update_table.setRowCount(len(updates))
                    for i, u in enumerate(updates):
                        if self.role == "admin" or u["ops"] == self.user_code:
                            self.update_table.setItem(i, 0, QTableWidgetItem(u.get("ops", "—")))
                            self.update_table.setItem(i, 1, QTableWidgetItem(u.get("hmj", "—")))
                            self.update_table.setItem(i, 2, QTableWidgetItem(u.get("haz", "—")))
                            self.update_table.setItem(i, 3, QTableWidgetItem(u.get("company", "—")))
                            self.update_table.setItem(i, 4, QTableWidgetItem(u.get("date", "—")))
                            self.update_table.setItem(i, 5, QTableWidgetItem(u.get("time", "—")))
                            update_item = QTableWidgetItem(u.get("update", "—"))
                            update_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                            self.update_table.setItem(i, 6, update_item)
            except Exception as e:
                print("❌ Failed to refresh updates:", e)

        def refresh_completed_tab(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/completed")
                if response.status_code == 200:
                    completed = response.json()
                    self.completed_table.setRowCount(len(completed))
                    for i, c in enumerate(completed):
                        self.completed_table.setItem(i, 0, QTableWidgetItem(c.get("ops", "—")))
                        self.completed_table.setItem(i, 1, QTableWidgetItem(c.get("company", "—")))
                        self.completed_table.setItem(i, 2, QTableWidgetItem(c.get("delivery_date", "—")))
                        self.completed_table.setItem(i, 3, QTableWidgetItem(c.get("time", "—")))
                        self.completed_table.setItem(i, 4, QTableWidgetItem(c.get("signed_by", "—")))
                        self.completed_table.setItem(i, 5, QTableWidgetItem(c.get("document", "—")))
                        self.completed_table.setItem(i, 6, QTableWidgetItem(c.get("pod", "—")))
            except Exception as e:
                print("❌ Failed to refresh completed:", e)

        def build_map_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            layout.addWidget(self.build_logo_header())

            map_view = QWebEngineView()

            html = f"""
            <!DOCTYPE html>
            <html>
              <head>
                <style>
                  html, body, #map {{ height:100%; margin:0; padding:0; }}
                </style>
                <script src="https://maps.googleapis.com/maps/api/js?key=AIzaSyCqimNSU2P32FU4be5Us4W87GLuliezU-8"></script>
                <script>
                  let map;
                  let driverMarkers = {{}};

                  function initMap() {{
                    const styledMapType = new google.maps.StyledMapType([
                      {{
                        "featureType": "all",
                        "elementType": "geometry",
                        "stylers": [{{ "color": "#F1F8E9" }}]
                      }},
                      {{
                        "featureType": "road",
                        "elementType": "geometry",
                        "stylers": [{{ "color": "#C8E6C9" }}]
                      }},
                      {{
                        "featureType": "water",
                        "elementType": "geometry",
                        "stylers": [{{ "color": "#AED581" }}]
                      }},
                      {{
                        "featureType": "poi",
                        "elementType": "labels.text.fill",
                        "stylers": [{{ "color": "#2E7D32" }}]
                      }},
                      {{
                        "featureType": "administrative",
                        "elementType": "labels.text.fill",
                        "stylers": [{{ "color": "#2E7D32" }}]
                      }}
                    ], {{ name: "Hazmat Style" }});

                    map = new google.maps.Map(document.getElementById("map"), {{
                      center: {{ lat: -26.2041, lng: 28.0473 }},
                      zoom: 10,
                      mapTypeControlOptions: {{
                        mapTypeIds: ["roadmap", "satellite", "styled_map"]
                      }},
                      disableDefaultUI: false,
                      zoomControl: true,
                      streetViewControl: false,
                      fullscreenControl: false
                    }});

                    map.mapTypes.set("styled_map", styledMapType);
                    map.setMapTypeId("styled_map");
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

            self.map_view = map_view
            return tab
        from PyQt6.QtWebEngineWidgets import QWebEngineView

        def build_deliveries_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            # Logo header
            layout.addWidget(self.build_logo_header())

            # Cinematic title strip
            title = QLabel("📦 Local Deliveries")
            title.setStyleSheet("""
                color: #2E7D32;
                font-size: 20px;
                font-weight: 600;
                padding: 12px;
                background-color: #F1F8E9;
                border-bottom: 2px solid #C8E6C9;
            """)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            # Filter bar
            filter_bar = QWidget()
            filter_layout = QHBoxLayout(filter_bar)
            filter_layout.setContentsMargins(20, 0, 20, 0)

            search_box = QLineEdit()
            search_box.setPlaceholderText("🔍 Filter by company or driver...")
            search_box.setStyleSheet("padding: 6px; border-radius: 4px; border: 1px solid #C8E6C9;")
            filter_layout.addWidget(search_box)

            refresh_btn = QPushButton("⟳ Refresh")
            refresh_btn.setStyleSheet("padding: 6px 12px;")
            filter_layout.addWidget(refresh_btn)

            layout.addWidget(filter_bar)

            # Deliveries table
            self.deliveries_table = QTableWidget()
            self.deliveries_table.setColumnCount(5)
            self.deliveries_table.setHorizontalHeaderLabels([
                "HAZ Ref#", "Company", "Pickup Date", "Driver", "Status"
            ])
            self.deliveries_table.verticalHeader().setDefaultSectionSize(40)
            self.deliveries_table.horizontalHeader().setStretchLastSection(True)
            self.deliveries_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.deliveries_table.setStyleSheet("""
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
                QTableWidget::item:hover {
                    background-color: #F1F8E9;
                }
            """)

            # Optional: status cell styling
            def style_status_cell(cell: QTableWidgetItem):
                status = cell.text().lower()
                if "pending" in status:
                    cell.setBackground(QColor("#FFF9C4"))
                    cell.setForeground(QColor("#F57F17"))
                elif "completed" in status:
                    cell.setBackground(QColor("#C8E6C9"))
                    cell.setForeground(QColor("#2E7D32"))
                elif "delayed" in status:
                    cell.setBackground(QColor("#FFCDD2"))
                    cell.setForeground(QColor("#C62828"))

            # Table container
            table_container = QWidget()
            table_layout = QVBoxLayout(table_container)
            table_layout.setContentsMargins(20, 10, 20, 10)
            table_layout.addWidget(self.deliveries_table)
            layout.addWidget(table_container)

            return tab

        def build_collections_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            # Logo header
            layout.addWidget(self.build_logo_header())

            # Cinematic title strip
            title = QLabel("📦 Active Collections")
            title.setStyleSheet("""
                color: #2E7D32;
                font-size: 20px;
                font-weight: 600;
                padding: 12px;
                background-color: #F1F8E9;
                border-bottom: 2px solid #C8E6C9;
            """)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            # Filter bar
            filter_bar = QWidget()
            filter_layout = QHBoxLayout(filter_bar)
            filter_layout.setContentsMargins(20, 0, 20, 0)

            search_box = QLineEdit()
            search_box.setPlaceholderText("🔍 Filter by company or driver...")
            search_box.setStyleSheet("padding: 6px; border-radius: 4px; border: 1px solid #C8E6C9;")
            filter_layout.addWidget(search_box)

            refresh_btn = QPushButton("⟳ Refresh")
            refresh_btn.setStyleSheet("padding: 6px 12px;")
            filter_layout.addWidget(refresh_btn)

            layout.addWidget(filter_bar)

            # Collections table
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
                QTableWidget::item:hover {
                    background-color: #F1F8E9;
                }
            """)

            # Optional: status cell styling
            def style_status_cell(cell: QTableWidgetItem):
                status = cell.text().lower()
                if "pending" in status:
                    cell.setBackground(QColor("#FFF9C4"))
                    cell.setForeground(QColor("#F57F17"))
                elif "completed" in status:
                    cell.setBackground(QColor("#C8E6C9"))
                    cell.setForeground(QColor("#2E7D32"))
                elif "delayed" in status:
                    cell.setBackground(QColor("#FFCDD2"))
                    cell.setForeground(QColor("#C62828"))

            # Table container
            table_container = QWidget()
            table_layout = QVBoxLayout(table_container)
            table_layout.setContentsMargins(20, 10, 20, 10)
            table_layout.addWidget(self.collections_table)
            layout.addWidget(table_container)

            return tab

        def filter_updates(self):
            """
            Filters the update_table rows based on the HMJ Ref# entered in the search bar.
            """
            query = self.search_input.text().strip().lower()

            for row in range(self.update_table.rowCount()):
                item = self.update_table.item(row, 1)  # Column 1 = HMJ Ref#
                if item and query in item.text().lower():
                    self.update_table.setRowHidden(row, False)
                else:
                    self.update_table.setRowHidden(row, True)

        def build_updates_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(20, 10, 20, 10)
            layout.setSpacing(16)

            # Header
            layout.addWidget(self.build_logo_header())

            title = QLabel("📦 Shipment Updates")
            title.setStyleSheet("""
                color: #1565C0;
                font-size: 20px;
                font-weight: 600;
                padding: 12px;
                background-color: #E3F2FD;
                border-bottom: 2px solid #90CAF9;
            """)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            # Form area
            form_bar = QWidget()
            form_layout = QHBoxLayout(form_bar)
            form_layout.setContentsMargins(20, 0, 20, 0)

            self.hmj_input = QLineEdit()
            self.hmj_input.setPlaceholderText("HMJ Ref")
            form_layout.addWidget(self.hmj_input)

            self.haz_input = QLineEdit()
            self.haz_input.setPlaceholderText("HAZJNB Ref")
            form_layout.addWidget(self.haz_input)

            self.company_input = QLineEdit()
            self.company_input.setPlaceholderText("Client Company")
            form_layout.addWidget(self.company_input)

            self.update_input = QLineEdit()
            self.update_input.setPlaceholderText("Latest Update")
            form_layout.addWidget(self.update_input)

            # Upload Document button
            upload_btn = QPushButton("📂 Upload Document")
            upload_btn.clicked.connect(self.upload_document)
            form_layout.addWidget(upload_btn)

            # Setup Email Addresses button
            email_btn = QPushButton("📧 Setup Client Emails")
            email_btn.clicked.connect(self.setup_client_emails)
            form_layout.addWidget(email_btn)

            # Add Shipment button
            add_btn = QPushButton("➕ Add Shipment")
            add_btn.clicked.connect(self.add_shipment)
            form_layout.addWidget(add_btn)

            layout.addWidget(form_bar)

            # Table
            self.updates_table = QTableWidget()
            self.updates_table.setColumnCount(8)
            self.updates_table.setHorizontalHeaderLabels([
                "Ops", "HMJ Ref", "HAZJNB Ref", "Company", "Date", "Time", "Latest Update", "Document"
            ])
            self.updates_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            layout.addWidget(self.updates_table)

            # Bottom buttons
            bottom_bar = QWidget()
            bottom_layout = QHBoxLayout(bottom_bar)
            bottom_layout.setContentsMargins(20, 0, 20, 0)

            update_btn = QPushButton("✏️ Update Shipment")
            update_btn.clicked.connect(self.update_shipment)
            bottom_layout.addWidget(update_btn)

            view_btn = QPushButton("👁 View Update")
            view_btn.clicked.connect(self.view_update)
            bottom_layout.addWidget(view_btn)

            layout.addWidget(bottom_bar)

            self.load_updates()
            return tab

        def upload_document(self):
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Document")
            if file_path:
                self.latest_document = file_path
                self.toast_manager.show_toast("📂 Document attached")

        def setup_client_emails(self):
            dialog = QDialog(self)
            dialog.setWindowTitle("Client Emails")
            dialog.resize(400, 200)
            layout = QVBoxLayout(dialog)

            email_input = QTextEdit()
            email_input.setPlaceholderText("Enter client emails (comma separated)")
            layout.addWidget(email_input)

            save_btn = QPushButton("Save")
            save_btn.clicked.connect(dialog.accept)
            layout.addWidget(save_btn)

            if dialog.exec() == QDialog.DialogCode.Accepted:
                emails = [e.strip() for e in email_input.toPlainText().split(",") if e.strip()]
                self.client_emails = emails

                # ✅ Save to DB for the selected shipment
                row = self.updates_table.currentRow()
                if row >= 0:
                    hmj = self.updates_table.item(row, 1).text()
                    conn = sqlite3.connect("hazmat.db")
                    cursor = conn.cursor()
                    cursor.execute("UPDATE updates SET client_emails = ? WHERE hmj = ?", (",".join(emails), hmj))
                    conn.commit()
                    conn.close()

                self.toast_manager.show_toast("📧 Client emails saved")

        def add_shipment(self):
            try:
                print("ADD_SHIPMENT — start")

                # Auto‑prefix HMJ and HAZJNB
                hmj_raw = self.hmj_input.text().strip()
                haz_raw = self.haz_input.text().strip()
                hmj = f"HMJ{hmj_raw}" if hmj_raw and not hmj_raw.upper().startswith("HMJ") else hmj_raw
                haz = f"HAZJNB{haz_raw}" if haz_raw and not haz_raw.upper().startswith("HAZJNB") else haz_raw

                company = self.company_input.text().strip()
                latest_update = self.update_input.text().strip()
                doc_path = getattr(self, "latest_document", "")
                emails_list = getattr(self, "client_emails", [])

                print(f"ADD_SHIPMENT — hmj={hmj} haz={haz} company={company} doc={doc_path} emails={emails_list}")

                conn = sqlite3.connect("hazmat.db")
                cursor = conn.cursor()

                # Duplicate check
                cursor.execute("SELECT id FROM updates WHERE hmj = ? OR haz = ?", (hmj, haz))
                dupe = cursor.fetchone()
                if dupe:
                    conn.close()
                    self.toast_manager.show_toast("⚠️ HMJ/HAZJNB Ref already exists")
                    return

                # Insert aligned with schema
                cursor.execute("""
                    INSERT INTO updates (ops, hmj, haz, company, date, time, latest_update, document, client_emails)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.user_code,
                    hmj,
                    haz,
                    company,
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M"),
                    latest_update,
                    doc_path,
                    ",".join(emails_list)
                ))
                conn.commit()
                conn.close()

                self.load_updates()
                self.toast_manager.show_toast("✅ Shipment added")

                # Mail subject includes HMJ and HAZ
                if emails_list:
                    subject = f"Shipment Update // ({hmj} // {haz})"
                    self.send_update_mail(subject, latest_update, doc_path)
            except Exception as e:
                print("ADD_SHIPMENT — error:", e)
                self.toast_manager.show_toast(f"⚠️ Add failed: {e}")

        def update_shipment(self):
            try:
                print("UPDATE_SHIPMENT — start")
                row = self.updates_table.currentRow()
                if row < 0:
                    self.toast_manager.show_toast("⚠️ Select a shipment first")
                    return

                hmj_item = self.updates_table.item(row, 1)  # HMJ column
                haz_item = self.updates_table.item(row, 2)  # HAZJNB column
                if not hmj_item or not haz_item:
                    self.toast_manager.show_toast("⚠️ Missing HMJ/HAZJNB Ref")
                    return

                # Auto‑prefix if needed
                hmj_raw = hmj_item.text().strip()
                haz_raw = haz_item.text().strip()
                hmj = f"HMJ{hmj_raw}" if hmj_raw and not hmj_raw.upper().startswith("HMJ") else hmj_raw
                haz = f"HAZJNB{haz_raw}" if haz_raw and not haz_raw.upper().startswith("HAZJNB") else haz_raw

                # Dialog for update text
                dialog = QDialog(self)
                dialog.setWindowTitle("Update Shipment")
                dialog.resize(600, 400)  # ✅ bigger window
                layout = QVBoxLayout(dialog)

                update_field = QLineEdit()
                update_field.setPlaceholderText("Enter latest update")
                layout.addWidget(update_field)

                save_btn = QPushButton("Save")
                save_btn.clicked.connect(dialog.accept)
                layout.addWidget(save_btn)

                if dialog.exec() == QDialog.DialogCode.Accepted:
                    latest_update = update_field.text().strip()
                    print(f"UPDATE_SHIPMENT — latest_update={latest_update}")
                    if latest_update:
                        conn = sqlite3.connect("hazmat.db")
                        cursor = conn.cursor()

                        # Update latest_update in DB
                        cursor.execute("UPDATE updates SET latest_update = ? WHERE hmj = ?", (latest_update, hmj))
                        conn.commit()

                        # Fetch client_emails + message_id for threading
                        cursor.execute("SELECT client_emails, message_id FROM updates WHERE hmj = ?", (hmj,))
                        result = cursor.fetchone()
                        conn.close()

                        self.load_updates()
                        self.toast_manager.show_toast("✅ Update finalized")

                        emails_list, original_msg_id = [], None
                        if result:
                            if result[0]:
                                emails_list = [e.strip() for e in result[0].split(",") if e.strip()]
                            if result[1]:
                                original_msg_id = result[1]

                        if emails_list:
                            subject = f"Shipment Update // ({hmj} // {haz})"

                            from sendgrid.helpers.mail import Mail
                            message = Mail(
                                from_email="jnb@hazglobal.com",
                                to_emails=emails_list,
                                subject=subject,
                                html_content=f"<p>{latest_update}</p>"
                            )

                            # ✅ Threading headers if we have original message ID
                            if original_msg_id:
                                message.headers = {
                                    "In-Reply-To": original_msg_id,
                                    "References": original_msg_id
                                }

                            try:
                                from sendgrid import SendGridAPIClient
                                sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
                                response = sg.send(message)

                                # ✅ Capture new Message-ID if returned
                                msg_id = None
                                if hasattr(response, "headers"):
                                    msg_id = response.headers.get("X-Message-Id")
                                if msg_id:
                                    conn = sqlite3.connect("hazmat.db")
                                    cursor = conn.cursor()
                                    cursor.execute("UPDATE updates SET message_id = ? WHERE hmj = ?", (msg_id, hmj))
                                    conn.commit()
                                    conn.close()

                                self.toast_manager.show_toast("📧 Mail sent successfully")
                            except Exception as e:
                                self.toast_manager.show_toast(f"❌ Mail failed: {str(e)}")
                        else:
                            print("UPDATE_SHIPMENT — no client emails, skipping mail")
            except Exception as e:
                print("UPDATE_SHIPMENT — error:", e)
                self.toast_manager.show_toast(f"⚠️ Update failed: {e}")

        def view_update(self):
            row = self.updates_table.currentRow()
            if row < 0:
                self.toast_manager.show_toast("⚠️ Select a shipment first")
                return

            latest_update = self.updates_table.item(row, 6).text()
            dialog = QDialog(self)
            dialog.setWindowTitle("View Update")
            layout = QVBoxLayout(dialog)

            label = QLabel(latest_update)
            layout.addWidget(label)

            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)

            dialog.exec()

        def send_update_mail(self, subject, update_text, doc_path="", hmj=None):
            emails = getattr(self, "client_emails", [])
            if not emails:
                print("⚠️ No client emails set, skipping mail")
                return

            try:
                from sendgrid import SendGridAPIClient
                from sendgrid.helpers.mail import Mail, Attachment
                import base64

                # Build message
                message = Mail(
                    from_email="jnb@hazglobal.com",
                    to_emails=emails,
                    subject=subject,
                    html_content=f"<p>{update_text}</p>"
                )

                # ✅ Attach document if present
                if doc_path and os.path.exists(doc_path):
                    with open(doc_path, "rb") as f:
                        data = f.read()
                    encoded = base64.b64encode(data).decode()
                    attachment = Attachment()
                    attachment.file_content = encoded
                    attachment.file_type = "application/octet-stream"
                    attachment.file_name = os.path.basename(doc_path)
                    attachment.disposition = "attachment"
                    message.attachment = attachment

                sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
                response = sg.send(message)

                print("DEBUG — API KEY loaded:", bool(os.environ.get("SENDGRID_API_KEY")))
                print("DEBUG — From email:", "jnb@hazglobal.com")
                print("DEBUG — To emails:", emails)
                print("DEBUG — Subject:", subject)
                print("DEBUG — Doc path:", doc_path, "Exists:", os.path.exists(doc_path))

                # ✅ Capture Message-ID for threading
                msg_id = None
                if hasattr(response, "headers"):
                    msg_id = response.headers.get("X-Message-Id")

                # Save Message-ID in DB for this shipment
                if msg_id and hmj:
                    conn = sqlite3.connect("hazmat.db")
                    cursor = conn.cursor()
                    cursor.execute("UPDATE updates SET message_id = ? WHERE hmj = ?", (msg_id, hmj))
                    conn.commit()
                    conn.close()

                self.toast_manager.show_toast("📧 Mail sent successfully")

            except Exception as e:
                self.toast_manager.show_toast(f"❌ Mail failed: {str(e)}")

        def build_completed_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)
            layout.setContentsMargins(20, 10, 20, 10)
            layout.setSpacing(16)

            # Logo header
            layout.addWidget(self.build_logo_header())

            # ✅ Branded title strip
            title = QLabel("✅ Completed Shipments")
            title.setStyleSheet("""
                color: #2E7D32;
                font-size: 20px;
                font-weight: 600;
                padding: 12px;
                background-color: #F1F8E9;
                border-bottom: 2px solid #C8E6C9;
            """)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title)

            # 🔍 Filter Bar + Export + Mail Report
            filter_bar = QWidget()
            filter_layout = QHBoxLayout(filter_bar)
            filter_layout.setContentsMargins(20, 0, 20, 0)

            self.completed_search_input = QLineEdit()
            self.completed_search_input.setPlaceholderText("🔍 Filter by Client or Invoice#...")
            self.completed_search_input.setStyleSheet("""
                QLineEdit {
                    padding: 6px;
                    border-radius: 4px;
                    border: 1px solid #C8E6C9;
                    font-size: 14px;
                    font-family: 'Segoe UI';
                }
            """)
            self.completed_search_input.textChanged.connect(self.filter_completed_shipments)
            filter_layout.addWidget(self.completed_search_input)

            clear_btn = QPushButton("✖ Clear")
            clear_btn.setFixedHeight(28)
            clear_btn.setStyleSheet("""
                QPushButton {
                    background-color: #C62828;
                    color: white;
                    border-radius: 4px;
                    font-size: 13px;
                    font-family: 'Segoe UI';
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #E53935;
                }
            """)
            clear_btn.clicked.connect(self.clear_completed_filter)
            filter_layout.addWidget(clear_btn)

            export_btn = QPushButton("📊 Export to Excel")
            export_btn.setFixedHeight(28)
            export_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2E7D32;
                    color: white;
                    border-radius: 4px;
                    font-size: 13px;
                    font-family: 'Segoe UI';
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #388E3C;
                }
            """)
            export_btn.clicked.connect(self.export_completed_to_excel)
            filter_layout.addWidget(export_btn)

            mail_btn = QPushButton("📧 Mail Report")
            mail_btn.setFixedHeight(28)
            mail_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1565C0;
                    color: white;
                    border-radius: 4px;
                    font-size: 13px;
                    font-family: 'Segoe UI';
                    padding: 4px 10px;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)
            mail_btn.clicked.connect(self.open_mail_dialog)
            filter_layout.addWidget(mail_btn)

            layout.addWidget(filter_bar)

            # 📋 Completed Table
            self.completed_table = QTableWidget()
            self.completed_table.setColumnCount(11)
            self.completed_table.setHorizontalHeaderLabels([
                "Ops", "HMJ Ref", "HAZJNB Ref", "Client", "Pickup Date",
                "Delivery Date", "Time", "Signed By", "Document", "POD", "Invoice#"
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
                QTableWidget::item:hover {
                    background-color: #F1F8E9;
                }
            """)
            self.completed_table.cellClicked.connect(self.handle_completed_click)
            layout.addWidget(self.completed_table)

            self.load_completed_shipments()
            return tab

        def filter_completed_shipments(self):
            query = self.completed_search_input.text().strip().lower()
            for row in range(self.completed_table.rowCount()):
                client = self.completed_table.item(row, 3)  # Client
                invoice = self.completed_table.item(row, 10)  # Invoice#
                match = False
                if client and query in client.text().lower():
                    match = True
                if invoice and query in invoice.text().lower():
                    match = True
                self.completed_table.setRowHidden(row, not match)

        def clear_completed_filter(self):
            self.completed_search_input.clear()
            for row in range(self.completed_table.rowCount()):
                self.completed_table.setRowHidden(row, False)

        def export_completed_to_excel(self):
            """
            Export visible rows to Excel, skipping Documents and POD columns.
            """
            import os, xlsxwriter
            from datetime import datetime
            from PyQt6.QtWidgets import QMessageBox

            documents_folder = os.path.join(os.path.expanduser("~"), "Documents")
            os.makedirs(documents_folder, exist_ok=True)

            filename = os.path.join(
                documents_folder,
                f"completed_shipments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )

            workbook = xlsxwriter.Workbook(filename)
            worksheet = workbook.add_worksheet("Completed Shipments")

            header_format = workbook.add_format({
                'bold': True, 'bg_color': '#2E7D32', 'font_color': 'white',
                'align': 'center', 'valign': 'vcenter', 'border': 1
            })
            row_format = workbook.add_format({'border': 1, 'font_name': 'Segoe UI', 'font_size': 11})
            alt_row_format = workbook.add_format(
                {'border': 1, 'bg_color': '#F1F8E9', 'font_name': 'Segoe UI', 'font_size': 11})
            date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1})

            # Headers (skip Document and POD)
            headers = [self.completed_table.horizontalHeaderItem(i).text()
                       for i in range(self.completed_table.columnCount())
                       if i not in (8, 9)]
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_format)
                worksheet.set_column(col, col, 18)

            # Data rows
            row_excel = 1
            for row in range(self.completed_table.rowCount()):
                if not self.completed_table.isRowHidden(row):
                    fmt = alt_row_format if row_excel % 2 == 0 else row_format
                    col_excel = 0
                    for col in range(self.completed_table.columnCount()):
                        if col in (8, 9):  # Skip Document and POD
                            continue
                        item = self.completed_table.item(row, col)
                        value = item.text() if item else ""
                        if col in (4, 5):  # Pickup Date, Delivery Date
                            try:
                                date_obj = datetime.strptime(value, "%Y-%m-%d")
                                worksheet.write_datetime(row_excel, col_excel, date_obj, date_format)
                            except:
                                worksheet.write(row_excel, col_excel, value, fmt)
                        else:
                            worksheet.write(row_excel, col_excel, value, fmt)
                        col_excel += 1
                    row_excel += 1

            workbook.close()
            self.toast_manager.show_toast("Report saved successfully")


        def open_mail_dialog(self):
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QPushButton

            dialog = QDialog(self)
            dialog.setWindowTitle("Send Report")
            layout = QVBoxLayout(dialog)

            email_input = QLineEdit()
            email_input.setPlaceholderText("Enter client email addresses (comma separated)")
            layout.addWidget(email_input)

            send_btn = QPushButton("Send")
            send_btn.clicked.connect(lambda: self.send_report(email_input.text(), dialog))
            layout.addWidget(send_btn)

            dialog.exec()

        def send_report(self, emails, dialog):
            # Export Excel first
            import os
            from datetime import datetime
            from PyQt6.QtWidgets import QMessageBox

            filename = os.path.join(
                os.path.expanduser("~"), "Documents",
                f"completed_shipments_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            )
            self.export_completed_to_excel()  # ensures file is created

            # --- SendGrid integration ---
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
            import base64

            try:
                # Prepare email
                message = Mail(
                    from_email="jnb@hazglobal.com",  # your sender email
                    to_emails=[e.strip() for e in emails.split(",")],
                    subject="Shipment Report",
                    html_content="<p>Please find attached your completed shipments report.</p>"
                )

                # Attach the Excel file
                with open(filename, "rb") as f:
                    data = f.read()
                    encoded = base64.b64encode(data).decode()
                    attachment = Attachment(
                        FileContent(encoded),
                        FileName(os.path.basename(filename)),
                        FileType("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                        Disposition("attachment")
                    )
                    message.attachment = attachment

                # Send
                sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))

                response = sg.send(message)

                dialog.accept()
                self.toast_manager.show_toast("Mail sent successfully")


            except Exception as e:
                QMessageBox.warning(self, "Mail Report", f"Failed to send report:\n{str(e)}")

        def load_completed_shipments(self):
            """
            Loads completed shipments into the completed_table.
            Replace this stub with actual database or API calls later.
            """
            # Clear table first
            self.completed_table.setRowCount(0)

            # Example dummy data for testing
            sample_data = [
                ["Ops1", "HMJ001", "HAZJNB001", "Client A", "2025-12-20", "2025-12-22", "10:00", "John Doe", "Doc1.pdf",
                 "POD1.pdf", "INV001"],
                ["Ops2", "HMJ002", "HAZJNB002", "Client B", "2025-12-21", "2025-12-23", "14:30", "Jane Smith",
                 "Doc2.pdf", "POD2.pdf", "INV002"],
            ]

            for row_data in sample_data:
                row = self.completed_table.rowCount()
                self.completed_table.insertRow(row)
                for col, value in enumerate(row_data):
                    self.completed_table.setItem(row, col, QTableWidgetItem(str(value)))

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
            try:
                print("LOAD_UPDATES — start")
                self.updates_table.setRowCount(0)
                conn = sqlite3.connect("hazmat.db")
                cursor = conn.cursor()
                cursor.execute("SELECT ops, hmj, haz, company, date, time, latest_update, document FROM updates")
                rows = cursor.fetchall()
                conn.close()
                print(f"LOAD_UPDATES — rows: {len(rows)}")

                for row_data in rows:
                    row_index = self.updates_table.rowCount()
                    self.updates_table.insertRow(row_index)
                    for col in range(8):
                        val = row_data[col] if col < len(row_data) else ""
                        item = QTableWidgetItem(str(val) if val is not None else "")
                        self.updates_table.setItem(row_index, col, item)
            except Exception as e:
                print("LOAD_UPDATES — error:", e)
                self.toast_manager.show_toast(f"⚠️ Failed to load updates: {e}")

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