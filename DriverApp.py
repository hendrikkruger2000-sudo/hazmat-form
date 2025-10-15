import sys, urllib.parse, requests, cv2
from PyQt6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from pyzbar.pyzbar import decode

DRIVER_CREDENTIALS = {
    "NT": {"password": "NT", "code": "NT"},       # Ntivulo Khosa
    "Kenny": {"password": "Kenny", "code": "Kenny"}  # Kenneth Rangata
}

BACKEND_URL = "https://hazmat-collection.onrender.com"

# -------------------- GPS Screen --------------------
class GPSScreen(QDialog):
    def __init__(self, address):
        super().__init__()
        self.setWindowTitle("GPS Navigation")
        self.setMinimumSize(600, 500)

        layout = QVBoxLayout(self)
        label = QLabel(f"Destination: {address}")
        label.setStyleSheet("color: #f2f2f2; font-size: 14px;")
        layout.addWidget(label)

        encoded = urllib.parse.quote(address)
        maps_url = f"https://www.google.com/maps/dir/?api=1&destination={encoded}"

        self.web_view = QWebEngineView()
        self.web_view.load(QUrl(maps_url))
        layout.addWidget(self.web_view)

# -------------------- Login Window --------------------
class DriverLogin(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hazmat Driver Login")
        self.setFixedSize(400, 300)

        self.setStyleSheet("""
            QDialog { background-color: #1c1c1c; }
            QLabel { color: #f2f2f2; font-size: 14px; }
            QLineEdit {
                background-color: #2e2e2e;
                color: #f2f2f2;
                border: 1px solid #444;
                padding: 6px;
            }
            QPushButton {
                background-color: #cc0000;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px;
            }
            QPushButton:hover {
                background-color: #ff0000;
            }
        """)

        layout = QVBoxLayout(self)

        logo = QLabel()
        pixmap = QPixmap("static/logo.png")
        logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("Driver Code")
        layout.addWidget(self.code_input)

        self.pass_input = QLineEdit()
        self.pass_input.setPlaceholderText("Password")
        self.pass_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self.pass_input)

        login_btn = QPushButton("Login")
        login_btn.clicked.connect(self.try_login)
        layout.addWidget(login_btn)

        self.driver_code = None

    def validate_login(self):
        username = self.code_input.text().strip()
        password = self.pass_input.text().strip()
        if username in DRIVER_CREDENTIALS and DRIVER_CREDENTIALS[username]["password"] == password:
            self.driver_code = DRIVER_CREDENTIALS[username]["code"]
            return True
        return False

    def try_login(self):
        if self.validate_login():
            self.accept()
        else:
            self.code_input.clear()
            self.pass_input.clear()
            self.code_input.setPlaceholderText("Invalid login. Try again.")

# -------------------- Dashboard Window --------------------
class DriverDashboard(QWidget):
    def __init__(self, driver_code):
        super().__init__()
        self.setWindowTitle("Hazmat Driver Dashboard")
        self.setMinimumSize(900, 600)
        self.driver_code = driver_code

        self.setStyleSheet("""
            QWidget { background-color: #1c1c1c; }
            QLabel { color: #f2f2f2; font-size: 14px; }
            QTableWidget {
                background-color: #2e2e2e;
                color: #f2f2f2;
                font-size: 13px;
                gridline-color: #444;
            }
            QHeaderView::section {
                background-color: #cc0000;
                color: white;
                font-size: 13px;
                padding: 6px;
            }
            QPushButton {
                background-color: #cc0000;
                color: white;
                font-weight: bold;
                border-radius: 6px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #ff0000;
            }
        """)

        layout = QVBoxLayout(self)

        logo = QLabel()
        pixmap = QPixmap("static/logo.png")
        logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        driver_label = QLabel(f"Logged in as: {driver_code}")
        driver_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(driver_label)

        self.collection_table = QTableWidget()
        self.collection_table.setColumnCount(7)
        self.collection_table.setHorizontalHeaderLabels([
            "HMJ Ref#", "HAZJNB Ref#", "Company", "Pickup Date", "Address", "Start", "Scan QR"
        ])
        layout.addWidget(QLabel("📦 Collections"))
        layout.addWidget(self.collection_table)

        self.delivery_table = QTableWidget()
        self.delivery_table.setColumnCount(7)
        self.delivery_table.setHorizontalHeaderLabels([
            "HAZ Ref#", "HAZJNB Ref#", "Company", "Delivery Date", "Address", "Start", "Scan QR"
        ])
        layout.addWidget(QLabel("🚚 Deliveries"))
        layout.addWidget(self.delivery_table)

        self.load_jobs()

    def load_jobs(self):
        try:
            res = requests.get(f"{BACKEND_URL}/driver/{self.driver_code}")
            jobs = res.json()
            self.collection_table.setRowCount(len(jobs))
            for i, job in enumerate(jobs):
                self.collection_table.setItem(i, 0, QTableWidgetItem(job.get("hmj_ref", "")))
                self.collection_table.setItem(i, 1, QTableWidgetItem(job["hazjnb_ref"]))
                self.collection_table.setItem(i, 2, QTableWidgetItem(job["company"]))
                self.collection_table.setItem(i, 3, QTableWidgetItem(job["pickup_date"]))
                self.collection_table.setItem(i, 4, QTableWidgetItem(job["address"]))

                start_btn = QPushButton("Start")
                start_btn.clicked.connect(lambda _, a=job["address"]: self.open_gps(a))
                self.collection_table.setCellWidget(i, 5, start_btn)

                qr_btn = QPushButton("Scan QR")
                qr_btn.clicked.connect(lambda _, r=job["hazjnb_ref"]: self.scan_qr(r))
                self.collection_table.setCellWidget(i, 6, qr_btn)
        except Exception as e:
            print("❌ Failed to load jobs:", e)

    def open_gps(self, address):
        gps = GPSScreen(address)
        gps.exec()

    def scan_qr(self, expected_ref):
        cap = cv2.VideoCapture(0)
        found = False

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            for barcode in decode(frame):
                qr_data = barcode.data.decode('utf-8')
                if qr_data == expected_ref:
                    found = True
                    cap.release()
                    cv2.destroyAllWindows()
                    try:
                        requests.post(f"{BACKEND_URL}/scan_qr", json={
                            "ref": expected_ref,
                            "driver_id": self.driver_code
                        })
                        print("✅ Scan confirmed")
                    except Exception as e:
                        print("❌ Scan error:", e)
                    return
                else:
                    cv2.putText(frame, "Invalid QR", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            cv2.imshow("Scan QR Code", frame)
            if cv2.waitKey(1) == 27:
                break

        cap.release()
        cv2.destroyAllWindows()
        if not found:
            print("QR scan cancelled or invalid.")

# -------------------- Main App --------------------
def main():
    app = QApplication(sys.argv)
    login = DriverLogin()
    if login.exec():
        driver_code = login.driver_code
        window = DriverDashboard(driver_code)
        window.show()
        sys.exit(app.exec())

if __name__ == "__main__":
    main()