import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QDialog,
    QTabWidget, QLineEdit, QTextEdit, QSizePolicy, QScrollArea,
    QHeaderView, QFileDialog, QDateEdit
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtCore import QUrl
from PyQt6.QtWidgets import QGridLayout
import requests

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("""
            QDialog {
                background-color: #1c1c1c;
            }
            QLabel {
                color: #f2f2f2;
                font-size: 14px;
            }
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
        self.setWindowTitle("Hazmat Global Login")
        layout = QVBoxLayout(self)

        # Logo
        logo = QLabel()
        pixmap = QPixmap("static/logo.png")
        logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # Username / Password / Button setup...

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.handle_login)

        layout.addWidget(QLabel("Enter your credentials:"))
        layout.addWidget(self.username_input)
        layout.addWidget(self.password_input)
        layout.addWidget(self.login_btn)
        self.setLayout(layout)

        self.role = None
        self.user_code = None

    def handle_login(self):
        users = {
            "hendrik": {"password": "hkpass", "role": "user", "code": "HK"},
            "morne": {"password": "mvpass", "role": "user", "code": "MV"},
            "justin": {"password": "jbpass", "role": "user", "code": "JB"},
            "admin": {"password": "adminpass", "role": "admin", "code": "ALL"}
        }

        username = self.username_input.text().lower()
        password = self.password_input.text()

        if username in users and users[username]["password"] == password:
            self.role = users[username]["role"]
            self.user_code = users[username]["code"]
            self.accept()
        else:
            self.username_input.setText("")
            self.password_input.setText("")
            self.username_input.setPlaceholderText("Invalid credentials")

class DashboardWindow(QMainWindow):
        def __init__(self, role, user_code):
            super().__init__()
            self.setStyleSheet("""
                        QMainWindow {
                            background-color: #1c1c1c;
                        }
                        QLabel {
                            color: #f2f2f2;
                            font-size: 14px;
                        }
                        QPushButton {
                            background-color: #cc0000;
                            color: white;
                            padding: 6px;
                            border-radius: 4px;
                        }
                        QPushButton:hover {
                            background-color: #ff0000;
                        }
                        QLineEdit, QTextEdit {
                            background-color: #2e2e2e;
                            color: #f2f2f2;
                            border: 1px solid #444;
                            padding: 4px;
                        }
                        QTabWidget::pane {
                            border: 1px solid #444;
                        }
                        QTabBar::tab {
                            background: #333;
                            color: #f2f2f2;
                            padding: 8px;
                        }
                        QTabBar::tab:selected {
                            background: #cc0000;
                        }
                    """)
            self.setWindowTitle("Hazmat Global Dashboard")
            self.role = role
            self.user_code = user_code
            self.init_ui()


        def load_live_collections(self):
            try:
                response = requests.get("https://hazmat-collection.onrender.com/ops/collections")
                if response.status_code == 200:
                    data = response.json()
                    self.unassigned_table.setRowCount(len(data))
                    for i, item in enumerate(data):
                        self.unassigned_table.setItem(i, 0, QTableWidgetItem("HMJ—"))  # Placeholder
                        self.unassigned_table.setItem(i, 1, QTableWidgetItem(item["hazjnb_ref"]))
                        self.unassigned_table.setItem(i, 2, QTableWidgetItem(item["company"]))
                        self.unassigned_table.setItem(i, 3, QTableWidgetItem(item["pickup_date"]))
                        self.unassigned_table.setItem(i, 4, QTableWidgetItem(item["address"]))
            except Exception as e:
                print("Failed to load collections from live site:", e)

        def select_driver(self, row, column):
            self.selected_driver_code = self.driver_table.item(row, 1).text()

        def select_collection(self, row, column):
            self.selected_collection_row = row
            address = self.unassigned_table.item(row, 4).text()
            encoded = address.replace(" ", "+")
            maps_url = f"https://www.google.com/maps/search/?api=1&query={encoded}"
            self.map_view.setText(f"<a href='{maps_url}' style='color:#f2f2f2;'>View on Google Maps</a>")
            self.map_view.setOpenExternalLinks(True)

        def assign_driver_to_collection(self):
            if hasattr(self, "selected_driver_code") and hasattr(self, "selected_collection_row"):
                driver_name = self.driver_table.item(0 if self.selected_driver_code == "NK" else 1, 0).text()
                self.unassigned_table.setItem(self.selected_collection_row, 2, QTableWidgetItem(driver_name))
                self.unassigned_table.setItem(self.selected_collection_row, 1, QTableWidgetItem(
                    self.unassigned_table.item(self.selected_collection_row,
                                               1).text() + f" ({self.selected_driver_code})"
                ))

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

        def build_map_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            # Scaled logo header
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaled(200, 40, Qt.AspectRatioMode.KeepAspectRatio))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)

            # Expanded map placeholder
            map_view = QLabel("🗺️ Google Maps integration placeholder")
            map_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
            map_view.setMinimumHeight(500)
            map_view.setStyleSheet("""
                background-color: #2e2e2e;
                color: #f2f2f2;
                font-size: 16px;
                border: 1px solid #444;
                padding: 20px;
            """)
            layout.addWidget(map_view)

            return tab

        def build_driver_tab(self):
            tab = QWidget()
            main_layout = QVBoxLayout(tab)
            main_layout.setContentsMargins(20, 10, 20, 10)
            main_layout.setSpacing(10)

            # Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            main_layout.addWidget(logo)

            # Top: Driver List (horizontal)
            driver_layout = QHBoxLayout()
            driver_label = QLabel("👤 Drivers")
            driver_label.setStyleSheet("color: #f2f2f2; font-size: 16px; font-weight: bold;")
            driver_layout.addWidget(driver_label)
            self.load_live_collections()
            self.driver_table = QTableWidget()
            self.driver_table.setColumnCount(2)
            self.driver_table.setHorizontalHeaderLabels(["Driver", "Code"])
            self.driver_table.setRowCount(2)
            self.driver_table.setItem(0, 0, QTableWidgetItem("Nikolas Renz"))
            self.driver_table.setItem(0, 1, QTableWidgetItem("NK"))
            self.driver_table.setItem(1, 0, QTableWidgetItem("Kenneth Ranaghan"))
            self.driver_table.setItem(1, 1, QTableWidgetItem("KR"))
            self.driver_table.cellClicked.connect(self.select_driver)
            self.driver_table.setMaximumHeight(100)
            driver_layout.addWidget(self.driver_table)
            main_layout.addLayout(driver_layout)

            # Middle: Collections Table + Assign Button
            collection_layout = QVBoxLayout()
            collection_label = QLabel("📦 New Collection Requests")
            collection_label.setStyleSheet("color: #f2f2f2; font-size: 16px; font-weight: bold;")
            collection_layout.addWidget(collection_label)

            self.unassigned_table = QTableWidget()
            self.unassigned_table.setColumnCount(5)
            self.unassigned_table.setHorizontalHeaderLabels([
                "HMJ Ref#", "HAZ Ref#", "Company", "Pickup Date", "Address"
            ])
            self.unassigned_table.setRowCount(2)
            self.unassigned_table.cellClicked.connect(self.select_collection)
            self.unassigned_table.setMaximumHeight(140)
            collection_layout.addWidget(self.unassigned_table)

            self.assign_btn = QPushButton("Assign Driver to Collection")
            self.assign_btn.setFixedHeight(32)
            self.assign_btn.setStyleSheet("""
                QPushButton {
                    background-color: #cc0000;
                    color: white;
                    font-weight: bold;
                    border-radius: 5px;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #ff0000;
                }
            """)
            self.assign_btn.clicked.connect(self.assign_driver_to_collection)
            collection_layout.addWidget(self.assign_btn)
            main_layout.addLayout(collection_layout)

            # Bottom: Map View (fills remaining space)
            self.map_view = QLabel("🗺️ Driver location map placeholder")
            self.map_view.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.map_view.setMinimumHeight(300)
            self.map_view.setStyleSheet("""
                background-color: #2e2e2e;
                color: #f2f2f2;
                font-size: 14px;
                border: 1px solid #444;
                padding: 10px;
            """)
            main_layout.addWidget(self.map_view)
            self.load_live_collections()
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
            self.collections_table.setColumnCount(6)
            self.collections_table.setHorizontalHeaderLabels([
                "HMJ Ref#", "HAZ Ref#", "Company", "Pickup Date", "Driver", "Status"
            ])
            self.collections_table.verticalHeader().setDefaultSectionSize(40)
            self.collections_table.horizontalHeader().setStretchLastSection(True)
            self.collections_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.collections_table.setStyleSheet("""
                QTableWidget {
                    background-color: #1c1c1c;
                    color: #f2f2f2;
                    font-size: 15px;
                    gridline-color: #444;
                }
                QHeaderView::section {
                    background-color: #cc0000;
                    color: white;
                    font-size: 16px;
                    padding: 8px;
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
            layout.setSpacing(10)

            # Logo
            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaled(160, 32, Qt.AspectRatioMode.KeepAspectRatio))
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo)

            # Form (compact)
            form_layout = QHBoxLayout()
            self.input_hmj = QLineEdit()
            self.input_hmj.setPlaceholderText("HMJ Ref#")
            self.input_haz = QLineEdit()
            self.input_haz.setPlaceholderText("HAZ Ref#")
            self.input_company = QLineEdit()
            self.input_company.setPlaceholderText("Company")
            self.input_update = QTextEdit()
            self.input_update.setPlaceholderText("Latest Update")
            self.input_update.setFixedHeight(60)
            submit_btn = QPushButton("Submit Update")
            submit_btn.clicked.connect(self.submit_update)

            form_layout.addWidget(self.input_hmj)
            form_layout.addWidget(self.input_haz)
            form_layout.addWidget(self.input_company)
            form_layout.addWidget(self.input_update)
            form_layout.addWidget(submit_btn)
            layout.addLayout(form_layout)

            # Update Table (clean layout)
            self.update_table = QTableWidget()
            self.update_table.setColumnCount(7)
            self.update_table.setHorizontalHeaderLabels([
                "Ops", "HMJ Ref#", "HAZ Ref#", "Company", "Date", "Time", "Latest Update"
            ])
            self.update_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
            for i in range(6):
                self.update_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            self.update_table.setStyleSheet("""
                QTableWidget {
                    background-color: #1c1c1c;
                    color: #f2f2f2;
                    font-size: 14px;
                    gridline-color: #444;
                }
                QHeaderView::section {
                    background-color: #cc0000;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
                }
            """)
            layout.addWidget(self.update_table)
            self.load_updates()

            return tab

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
            self.completed_table.setColumnCount(7)
            self.completed_table.setHorizontalHeaderLabels([
                "Ops", "Company", "Delivery Date", "Time", "Signed By", "Document", "POD"
            ])
            self.completed_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.completed_table.setStyleSheet("""
                QTableWidget {
                    background-color: #1c1c1c;
                    color: #f2f2f2;
                    font-size: 14px;
                    gridline-color: #444;
                }
                QHeaderView::section {
                    background-color: #cc0000;
                    color: white;
                    font-size: 14px;
                    padding: 6px;
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
