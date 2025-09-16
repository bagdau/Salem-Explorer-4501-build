# modules/mods_ui.py
# -*- coding: utf-8 -*-
import os
from typing import Optional
from PyQt5.QtCore import Qt, QSize, QUrl
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QCheckBox, QFrame, QLineEdit, QDialog, QSplitter
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage

from .mods_loader import ModLoader, Mod


class _PreviewPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        print(f"[Mod Preview JS] {message} ({source}:{line})")


class ModPreviewDialog(QDialog):
    """Превью одного мода: отдельный вебвью, инъекция только выбранного мода."""
    def __init__(self, loader: ModLoader, mod: Mod, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"Превью — {mod.name}")
        self.setModal(False)
        self.resize(980, 720)
        self.loader, self.mod = loader, mod

        root = QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(8)

        bar = QHBoxLayout(); bar.setSpacing(6)
        self.addr = QLineEdit(); self.addr.setPlaceholderText("URL для превью (например, https://example.com)")
        # предположим, что автор мода указал какую-то «домашнюю» ссылку
        def guess():
            for k in ("homepage", "homepage_url", "home", "preview", "preview_url"):
                if k in mod.manifest:
                    return str(mod.manifest.get(k))
            return "https://example.com"
        self.addr.setText(guess())

        btn_go = QPushButton("Открыть")
        btn_inject = QPushButton("Инъекция")
        btn_inject.setToolTip("Переинъецировать мод на текущую страницу")

        bar.addWidget(QLabel(f"<b>{mod.name}</b> v{mod.version}"))
        bar.addStretch(1)
        bar.addWidget(self.addr, 1)
        bar.addWidget(btn_go)
        bar.addWidget(btn_inject)
        root.addLayout(bar)

        self.web = QWebEngineView(self)
        self.web.setPage(_PreviewPage(self.web))
        root.addWidget(self.web, 1)

        btn_go.clicked.connect(self._go)
        btn_inject.clicked.connect(self._inject_now)

        self._go()

    def _go(self):
        url = self.addr.text().strip()
        if "://" not in url:
            url = "http://" + url
        self.web.setUrl(QUrl(url))

    def _inject_now(self):
        self.loader.inject_mod_into_view(self.web, self.mod)


class ModManager(QWidget):
    def __init__(self, loader: ModLoader, parent: Optional[QWidget] = None, as_page=False):
        super().__init__(parent)
        self.setObjectName("ModManager")
        self.loader = loader
        self.as_page = as_page
        self.setStyleSheet(self._qss())

        root = QVBoxLayout(self); root.setContentsMargins(10,10,10,10); root.setSpacing(8)

        # Шапка
        cap = QLabel("Моды"); cap.setObjectName("Caption")
        root.addWidget(cap)

        # Кнопки действий
        actions = QHBoxLayout(); actions.setSpacing(6)

        btn_add_zip = QPushButton("Установить ZIP…"); btn_add_zip.clicked.connect(self._install_zip)
        btn_add_dir = QPushButton("Импорт из папки…"); btn_add_dir.clicked.connect(self._install_dir)
        btn_open = QPushButton("Открыть папку"); btn_open.clicked.connect(self._open_dir)
        btn_refresh = QPushButton("Обновить"); btn_refresh.clicked.connect(self._reload)

        actions.addWidget(btn_add_zip)
        actions.addWidget(btn_add_dir)
        actions.addWidget(btn_open)
        actions.addStretch(1)
        actions.addWidget(btn_refresh)
        root.addLayout(actions)

        # Список модов
        self.listw = QListWidget(); self.listw.setUniformItemSizes(True)
        root.addWidget(self.listw, 1)

        # Подсказка про фейковый адрес
        hint = QLabel('Подсказка: открыть эту страницу можно по адресу <code>salem://mods</code> или <code>about:mods</code>.')
        hint.setStyleSheet("color:#8aa0b6;")
        root.addWidget(hint)

        self._reload()

    # ── обработчики ───────────────────────────────────────────────────
    def _install_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, "Установить мод (ZIP)", "", "ZIP архив (*.zip)")
        if not path: 
            return
        try:
            mod = self.loader.install_zip(path)
            self._reload()
            if mod:
                QMessageBox.information(self, "Установлено", f"Мод «{mod.name}» установлен и включён.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка установки", f"{e}")

    def _install_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Импорт мода из папки", "")
        if not d: return
        try:
            mod = self.loader.install_dir(d)
            self._reload()
            if mod:
                QMessageBox.information(self, "Импортировано", f"Мод «{mod.name}» импортирован и включён.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка импорта", f"{e}")

    def _open_dir(self):
        d = self.loader.open_dir()
        try:
            import subprocess, sys
            if sys.platform.startswith("win"):
                subprocess.Popen(f'explorer "{d}"')
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception:
            QMessageBox.information(self, "Папка модов", d)

    def _reload(self):
        self.loader.reload()
        self.listw.clear()
        for m in self.loader.list_mods():
            self._add_item(m)

    def _add_item(self, mod: Mod):
        item = QListWidgetItem()
        row = self._row(mod)
        item.setSizeHint(QSize(10, 96))
        self.listw.addItem(item)
        self.listw.setItemWidget(item, row)

    def _row(self, mod: Mod) -> QWidget:
        box = QFrame(); box.setObjectName("ModCard")
        lay = QHBoxLayout(box); lay.setContentsMargins(12,12,12,12); lay.setSpacing(10)

        icon = QLabel(); icon.setFixedSize(40,40); icon.setObjectName("Icon")
        pm = QPixmap(mod.icon_path) if mod.icon_path else QPixmap(40,40); 
        if pm.isNull(): pm = QPixmap(40,40); pm.fill(Qt.transparent)
        icon.setPixmap(pm.scaled(40,40, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        text = QVBoxLayout(); text.setSpacing(2)
        name = QLabel(f"{mod.name}"); name.setObjectName("Title")
        meta = QLabel(f"{mod.id} · v{mod.version}"); meta.setObjectName("Meta")
        desc = QLabel(mod.description or "—"); desc.setObjectName("Desc"); desc.setWordWrap(True)
        text.addWidget(name); text.addWidget(meta); text.addWidget(desc)

        # Колонка управления: тумблер, порядок, превью, удалить
        col = QVBoxLayout(); col.setSpacing(6)

        cb = QCheckBox("Включён"); cb.setChecked(mod.enabled)
        cb.toggled.connect(lambda v, mid=mod.id: self.loader.enable(mid, v))

        order = QHBoxLayout(); order.setSpacing(6)
        up = QPushButton("↑"); down = QPushButton("↓")
        up.clicked.connect(lambda _, mid=mod.id: (self.loader.move(mid, -1), self._reload()))
        down.clicked.connect(lambda _, mid=mod.id: (self.loader.move(mid, +1), self._reload()))
        order.addWidget(up); order.addWidget(down)

        preview = QPushButton("Превью…")
        preview.clicked.connect(lambda _, m=mod: ModPreviewDialog(self.loader, m, self).show())

        btn_del = QPushButton("Удалить"); btn_del.setProperty("destructive", True)
        btn_del.clicked.connect(lambda _, mid=mod.id: self._remove_confirm(mid))

        col.addWidget(cb)
        col.addLayout(order)
        col.addWidget(preview)
        col.addWidget(btn_del)

        lay.addWidget(icon)
        lay.addLayout(text, 1)
        lay.addLayout(col)

        return box

    def _remove_confirm(self, mod_id: str):
        m = self.loader.get(mod_id)
        if not m: return
        if QMessageBox.question(self, "Удалить мод", f"Удалить «{m.name}»?") == QMessageBox.Yes:
            self.loader.remove(mod_id)
            self._reload()

    # ── стиль ─────────────────────────────────────────────────────────
    def _qss(self) -> str:
        return """
        QWidget#ModManager { background:#0f1117; color:#e6edf3; }
        QLabel#Caption { font-size:18px; font-weight:700; padding:4px 6px;
            border-bottom:2px solid qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #22d3ee, stop:1 #6E9CFF); }
        QListWidget { border:1px solid #223046; border-radius:10px; background:transparent; }
        QFrame#ModCard { background:#0b0e14; border:1px solid #1e293b; border-radius:12px; }
        QLabel#Title { font-weight:600; font-size:15px; }
        QLabel#Meta { color:#8aa0b6; font-size:12px; }
        QLabel#Desc { color:#b7c5d3; font-size:13px; }
        QPushButton { background:#111827; border:1px solid #223046; border-radius:8px; padding:6px 10px; color:#e6edf3; }
        QPushButton:hover { background:#172131; border-color:#22d3ee; color:#bfefff; }
        QPushButton[destructive="true"] { background:#2b0f18; border:1px solid #7a243a; }
        QPushButton[destructive="true"]:hover { background:#3a1522; border-color:#a8324f; }
        QCheckBox { padding:2px; }
        """
