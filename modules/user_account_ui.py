
from PyQt5.QtWidgets import QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout, QMessageBox
import json
import os

USER_DATA_FILE = "user_data.json"

class UserAccountPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Аккаунт пользователя")
        self.setGeometry(300, 200, 300, 200)

        self.name_label = QLabel("Имя:")
        self.name_input = QLineEdit()

        self.email_label = QLabel("Email:")
        self.email_input = QLineEdit()

        self.password_label = QLabel("Пароль:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)

        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self.save_user_data)

        layout = QVBoxLayout()
        layout.addWidget(self.name_label)
        layout.addWidget(self.name_input)
        layout.addWidget(self.email_label)
        layout.addWidget(self.email_input)
        layout.addWidget(self.password_label)
        layout.addWidget(self.password_input)
        layout.addWidget(self.save_btn)
        self.setLayout(layout)

        self.load_user_data()

    def save_user_data(self):
        data = {
            "name": self.name_input.text(),
            "email": self.email_input.text(),
            "password": self.password_input.text()
        }
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
        QMessageBox.information(self, "Успешно", "Данные сохранены!")

    def load_user_data(self):
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.name_input.setText(data.get("name", ""))
                self.email_input.setText(data.get("email", ""))
                self.password_input.setText(data.get("password", ""))
