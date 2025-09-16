
from PyQt5.QtWidgets import QListWidget

class DownloadsPanelController:
    def __init__(self, parent=None):
        self.panel = QListWidget(parent)
        self.panel.hide()

    def toggle(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.show()

    def update_downloads(self, file_path: str):
        self.panel.addItem(f"✅ Жүктелді: {file_path}")
        self.panel.show()
