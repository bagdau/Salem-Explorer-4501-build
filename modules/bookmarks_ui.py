from PyQt5.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QLabel, QMessageBox
)
from PyQt5.QtCore import Qt

from modules.bookmarks import BookmarksManager

class BookmarksUI(QWidget):
    def __init__(self, bookmarks_manager, on_open_url=None):
        super().__init__()
        self.manager = bookmarks_manager
        self.on_open_url = on_open_url  # callback-функция для открытия url

        self.setWindowTitle("Закладки")
        self.resize(400, 350)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self._open_bookmark)
        self._update_list()

        # --- Кнопки и поля ---
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Название страницы")
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("URL страницы")
        btn_add = QPushButton("Добавить")
        btn_add.clicked.connect(self._add_bookmark)

        btn_remove = QPushButton("Удалить выбранное")
        btn_remove.clicked.connect(self._remove_selected)

        # Layout
        fields = QHBoxLayout()
        fields.addWidget(QLabel("Название:"))
        fields.addWidget(self.input_title)
        fields.addWidget(QLabel("URL:"))
        fields.addWidget(self.input_url)
        fields.addWidget(btn_add)

        main_layout = QVBoxLayout()
        main_layout.addWidget(QLabel("<b>Закладки:</b>"))
        main_layout.addWidget(self.list)
        main_layout.addLayout(fields)
        main_layout.addWidget(btn_remove)
        self.setLayout(main_layout)

    def _update_list(self):
        self.list.clear()
        for bm in self.manager.get_all():
            self.list.addItem(f"{bm['title']} — {bm['url']}")

    def _add_bookmark(self):
        title = self.input_title.text().strip()
        url = self.input_url.text().strip()
        if not title or not url:
            QMessageBox.warning(self, "Ошибка", "Введите название и URL!")
            return
        self.manager.add(title, url)
        self._update_list()
        self.input_title.clear()
        self.input_url.clear()

    def _remove_selected(self):
        idx = self.list.currentRow()
        if idx == -1:
            QMessageBox.information(self, "Нет выбора", "Выберите закладку для удаления.")
            return
        bm = self.manager.get_all()[idx]
        self.manager.remove(bm['url'])
        self._update_list()

    def _open_bookmark(self, item):
        idx = self.list.currentRow()
        bm = self.manager.get_all()[idx]
        if self.on_open_url:
            self.on_open_url(bm['url'])
        else:
            QMessageBox.information(self, "URL", bm['url'])

# ======== Пример использования ========
if __name__ == "__main__":
    import sys
    from PyQt5.QtWidgets import QApplication

    def open_url(url):
        print("Открыть URL:", url)  # Здесь вставляй переход в свой webview

    app = QApplication(sys.argv)
    manager = BookmarksManager()
    ui = BookmarksUI(manager, on_open_url=open_url)
    ui.show()
    sys.exit(app.exec_())
