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

class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Hazmat Global Login")
        layout = QVBoxLayout()
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
            layout = QVBoxLayout()
            layout.addWidget(QLabel("🗺️ Map view placeholder"))
            tab.setLayout(layout)
            return tab

        def build_driver_tab(self):
            tab = QWidget()
            layout = QVBoxLayout()
            layout.addWidget(QLabel("🚚 Driver selector placeholder"))
            tab.setLayout(layout)
            return tab

        def build_collections_tab(self):
            tab = QWidget()
            layout = QVBoxLayout()
            layout.addWidget(QLabel("📦 Collections placeholder"))
            tab.setLayout(layout)
            return tab

        def build_updates_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            logo = QLabel()
            pixmap = QPixmap("static/logo.png")
            logo.setPixmap(pixmap.scaledToHeight(60))
            layout.addWidget(logo)

            form_layout = QHBoxLayout()
            self.input_hmj = QLineEdit()
            self.input_hmj.setPlaceholderText("HMJ Ref#")
            self.input_haz = QLineEdit()
            self.input_haz.setPlaceholderText("HAZ Ref#")
            self.input_company = QLineEdit()
            self.input_company.setPlaceholderText("Company Name")
            form_layout.addWidget(self.input_hmj)
            form_layout.addWidget(self.input_haz)
            form_layout.addWidget(self.input_company)
            layout.addLayout(form_layout)

            self.input_update = QTextEdit()
            self.input_update.setPlaceholderText("Latest Update")
            layout.addWidget(self.input_update)

            submit_btn = QPushButton("Submit Update")
            submit_btn.clicked.connect(self.submit_update)
            layout.addWidget(submit_btn)

            self.update_table = QTableWidget()
            self.update_table.setColumnCount(7)
            self.update_table.setHorizontalHeaderLabels([
                "Ops", "HMJ Ref#", "HAZ Ref#", "Company", "Date", "Time", "Latest Update"
            ])
            self.update_table.setWordWrap(True)
            self.update_table.verticalHeader().setDefaultSectionSize(60)
            self.update_table.cellClicked.connect(self.handle_cell_click)
            layout.addWidget(self.update_table)

            self.load_updates()
            return tab

        def build_completed_tab(self):
            tab = QWidget()
            layout = QVBoxLayout(tab)

            self.completed_table = QTableWidget()
            self.completed_table.setColumnCount(7)
            self.completed_table.setHorizontalHeaderLabels([
                "Ops", "Company", "Delivery Date", "Delivery Time", "Signed By", "Document", "POD"
            ])
            self.completed_table.cellDoubleClicked.connect(self.handle_completed_click)
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
            sample = [
                {"ops": "HK", "hmj": "HMJ001", "haz": "HAZ001", "company": "COOPERS", "date": "2025-10-14",
                 "time": "22:07", "update": "Initial load"},
                {"ops": "MV", "hmj": "HMJ002", "haz": "HAZ002", "company": "MINEX", "date": "2025-10-14",
                 "time": "22:08", "update": "Delayed"},
            ]
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
