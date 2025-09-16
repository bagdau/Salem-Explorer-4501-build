from __future__ import annotations

import os
import json
import shutil
from tkinter.ttk import Widget
import traceback
from dataclasses import dataclass
from typing import List, Optional

from PyQt5.QtCore import Qt, QSize, QTimer, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QKeySequence, QFont
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QToolButton, QLineEdit, QScrollArea, QFrame, QFileDialog, QMessageBox,
    QCheckBox, QShortcut, QDialog, QTabWidget, QTextBrowser, QPlainTextEdit
)

# ------------------------------ helpers ------------------------------

def _is_win() -> bool:
    return os.name == "nt"

def _open_folder(path: str) -> None:
    try:
        if _is_win():
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    except Exception:
        pass

@dataclass
class ExtInfo:
    name: str
    path: str
    enabled: bool = True
    version: str = ""
    description: str = ""
    author: str = ""


# ------------------------------ Info Dialog (styled) ------------------------------

class ExtInfoDialog(QDialog):
    """Тёмный, аккуратный диалог с вкладками: README / manifest.json.
    Только UI/дизайн — логика минимальна, без сторонних либ.
    """
    def __init__(self, info: ExtInfo, manifest_text: str, readme_text: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"ℹ️ {info.name}")
        self.setModal(True)
        self.resize(720, 560)
        self.setMinimumSize(600, 420)
        self.setObjectName("ExtInfoDialog")

        root = QVBoxLayout(self); root.setContentsMargins(12, 12, 12, 12); root.setSpacing(10)

        # Header
        head = QVBoxLayout(); head.setSpacing(6)
        title = QLabel(info.name); title.setObjectName("InfoTitle")
        chips = QHBoxLayout(); chips.setSpacing(6)
        chip_ver = QLabel(f"v{info.version}" if info.version else "–"); chip_ver.setObjectName("Chip")
        chip_auth = QLabel(info.author or "Автор неизвестен"); chip_auth.setObjectName("Chip")
        chips.addWidget(chip_ver); chips.addWidget(chip_auth); chips.addStretch(1)

        subtitle = QLabel(info.description or info.path); subtitle.setObjectName("InfoSub")
        head.addWidget(title)
        head.addLayout(chips)
        head.addWidget(subtitle)
        root.addLayout(head)

        # Actions row (open folder/manifest, copy path)
        actions = QHBoxLayout(); actions.setSpacing(8)
        btn_open_folder = QPushButton("📁 Папка расширения")
        btn_open_manifest = QPushButton("{} manifest.json")
        btn_copy_path = QPushButton("📋 Копировать путь")
        actions.addWidget(btn_open_folder)
        actions.addWidget(btn_open_manifest)
        actions.addStretch(1)
        actions.addWidget(btn_copy_path)
        root.addLayout(actions)

        # Tabs: README / manifest.json
        tabs = QTabWidget(); tabs.setObjectName("InfoTabs")

        # README / Description
        readme = QTextBrowser(); readme.setOpenExternalLinks(True); readme.setObjectName("Readme")
        readme.setStyleSheet("QTextBrowser{background:#0b111a;border:1px solid #1e293b;border-radius:10px;color:#e6e8ee;padding:10px}")
        # Пытаемся markdown, иначе как preformatted
        md = (readme_text or "").strip()
        if md:
            try:
                # Qt >= 5.14
                readme.setMarkdown(md)
            except Exception:
                from html import escape
                readme.setHtml(f"<pre style='white-space:pre-wrap;font-family:Consolas,monospace'>{escape(md)}</pre>")
        else:
            readme.setHtml("<div style='color:#93a1b1'>Описание не найдено.</div>")

        tabs.addTab(readme, "Описание")

        # manifest.json
        manifest = QPlainTextEdit(); manifest.setReadOnly(True); manifest.setObjectName("Manifest")
        manifest.setPlainText((manifest_text or "{}").strip() or "{}")
        mf_font = QFont("Consolas"); mf_font.setStyleHint(QFont.Monospace)
        manifest.setFont(mf_font)
        tabs.addTab(manifest, "manifest.json")

        root.addWidget(tabs, 1)

        # Footer buttons
        foot = QHBoxLayout(); foot.setSpacing(8)
        btn_copy_json = QPushButton("📋 Скопировать JSON")
        btn_save_json = QPushButton("💾 Сохранить JSON…")
        btn_close = QPushButton("Закрыть")
        foot.addWidget(btn_copy_json); foot.addWidget(btn_save_json)
        foot.addStretch(1)
        foot.addWidget(btn_close)
        root.addLayout(foot)

        # Wire actions
        btn_open_folder.clicked.connect(lambda: _open_folder(info.path))
        def _open_manifest():
            p = os.path.join(info.path, "manifest.json")
            if os.path.isfile(p):
                QDesktopServices.openUrl(QUrl.fromLocalFile(p))
            else:
                QMessageBox.information(self, "manifest.json", "Файл не найден.")
        btn_open_manifest.clicked.connect(_open_manifest)

        btn_copy_path.clicked.connect(lambda: self._copy_to_clip(info.path))
        btn_copy_json.clicked.connect(lambda: self._copy_to_clip(manifest.toPlainText()))
        btn_save_json.clicked.connect(lambda: self._save_json_to_file(info.path, manifest.toPlainText()))
        btn_close.clicked.connect(self.accept)

        # Style
        self.setStyleSheet(self._qss())

    def _copy_to_clip(self, text: str):
        try:
            from PyQt5.QtWidgets import QApplication
            QApplication.clipboard().setText(text or "")
        except Exception:
            pass

    def _save_json_to_file(self, base_path: str, content: str):
        p = os.path.join(base_path, "manifest.json")
        try:
            fname, _ = QFileDialog.getSaveFileName(self, "Сохранить manifest.json", p, "JSON (*.json)")
            if not fname:
                return
            with open(fname, "w", encoding="utf-8") as f:
                f.write(content)
            QMessageBox.information(self, "Сохранено", os.path.basename(fname))
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def _qss(self) -> str:
        return """
        QWidget#ExtInfoDialog { background:#0f1117; color:#e6e8ee; }
        QLabel#InfoTitle { font-size:20px; font-weight:800; color:#e6e8ee; }
        QLabel#InfoSub { color:#a9b6c8; }
        QLabel#Chip {
            padding:2px 8px; border-radius:8px; background:#1b2636;
            border:1px solid #253246; color:#a7b8cf; font: 10pt "Segoe UI";
        }
        QTabWidget::pane { border: 1px solid #1e293b; border-radius:10px; padding:2px; background:#0b111a; }
        QTabBar::tab { padding:6px 12px; color:#c8d2e4; background:#0f141b; border:1px solid #1e293b; border-bottom:none; border-top-left-radius:8px; border-top-right-radius:8px; margin-right:4px; }
        QTabBar::tab:selected { background:#162033; color:#e6e8ee; }
        QPlainTextEdit#Manifest { background:#0b111a; border:1px solid #1e293b; border-radius:10px; color:#e6e8ee; padding:8px; }
        QPushButton { background:#111827; border:1px solid #223046; border-radius:8px; padding:8px 12px; color:#e6e8ee; }
        QPushButton:hover { border-color:#3b82f6; color:#dbe8ff; }
        """


# ------------------------------ Card ------------------------------

class ExtCard(QFrame):
    def __init__(self, info: ExtInfo, mgr: "ExtensionManager"):
        super().__init__(mgr)
        self.mgr = mgr
        self.info = info
        self.setObjectName("ExtCard")
        self.setMinimumHeight(92)

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(12)

        # left
        left = QVBoxLayout(); left.setSpacing(4)
        self.title = QLabel(info.name); self.title.setObjectName("ExtTitle")
        bits = []
        if info.version: bits.append(f"v{info.version}")
        if info.author:  bits.append(info.author)
        self.meta = QLabel("  ·  ".join(bits)); self.meta.setObjectName("ExtMeta")
        self.desc = QLabel(info.description or info.path); self.desc.setObjectName("ExtDesc"); self.desc.setWordWrap(True)
        left.addWidget(self.title); left.addWidget(self.meta); left.addWidget(self.desc)

        # right
        right = QHBoxLayout(); right.setSpacing(6)
        self.toggle = QCheckBox("Включено")
        self.toggle.setChecked(bool(info.enabled))
        self.toggle.stateChanged.connect(self._on_toggle)

        self.btn_reload = QToolButton(); self.btn_reload.setText("🔄"); self.btn_reload.setToolTip("Перезагрузить")
        self.btn_reload.clicked.connect(lambda: self.mgr._reload_one(self.info.name))

        self.btn_folder = QToolButton(); self.btn_folder.setText("📁"); self.btn_folder.setToolTip("Открыть папку")
        self.btn_folder.clicked.connect(lambda: _open_folder(self.info.path))

        self.btn_info = QToolButton(); self.btn_info.setText("ℹ️"); self.btn_info.setToolTip("Информация")
        self.btn_info.clicked.connect(lambda: self.mgr.show_extension_info(self.info))

        for b in (self.btn_reload, self.btn_folder, self.btn_info):
            b.setFixedSize(32, 32); b.setCursor(Qt.PointingHandCursor)

        right.addWidget(self.toggle)
        right.addWidget(self.btn_reload)
        right.addWidget(self.btn_folder)
        right.addWidget(self.btn_info)

        root.addLayout(left, 1)
        root.addLayout(right, 0)

    def _on_toggle(self, state: int):
        en = state == Qt.Checked
        try:
            self.mgr._enable_ext(self.info.name, en)
            self.mgr.toast(f"{self.info.name}: {'включено' if en else 'выключено'}")
        except Exception as e:
            self.mgr.toast(f"Ошибка: {e}")
            self.toggle.blockSignals(True)
            self.toggle.setChecked(not en)
            self.toggle.blockSignals(False)


# ------------------------------ Manager ------------------------------

class ExtensionManager(QWidget):
    # если окно открыли НЕ во вкладке, эта кнопка в хедере предлагает "Открыть как вкладку"
    requestOpenInTab = pyqtSignal()

    def __init__(self, loader, parent: Optional[Widget] = None, *, as_page: bool = False):
        super().__init__(parent)
        self.loader = loader
        self.as_page = bool(as_page)
        self.setObjectName("ExtensionsManager")

        # директория с расширениями
        self.extensions_dir = os.path.abspath(getattr(loader, "extensions_dir", "extensions"))
        os.makedirs(self.extensions_dir, exist_ok=True)

        # окно/страница
        if not self.as_page:
            self.setWindowTitle("🧩 Extensions Manager")
            self.resize(860, 640)
            self.setMinimumSize(700, 520)
            # ESC -> закрыть
            QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)

        # layout
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # header
        hdr = QHBoxLayout(); hdr.setSpacing(8)
        self.caption = QLabel("Расширения"); self.caption.setObjectName("Caption")
        hdr.addWidget(self.caption, 1)

        self.btn_open_tab = QToolButton(); self.btn_open_tab.setText("📎"); self.btn_open_tab.setToolTip("Открыть как вкладку")
        self.btn_open_tab.clicked.connect(lambda: self.requestOpenInTab.emit())
        self.btn_open_tab.setVisible(not self.as_page)
        hdr.addWidget(self.btn_open_tab)

        self.btn_close = QToolButton(); self.btn_close.setText("✖"); self.btn_close.setToolTip("Закрыть")
        self.btn_close.clicked.connect(self.close)
        self.btn_close.setVisible(not self.as_page)  # во вкладке закрывает саму вкладку
        hdr.addWidget(self.btn_close)

        root.addLayout(hdr)

        # toolbar
        bar = QHBoxLayout(); bar.setSpacing(8)
        self.search = QLineEdit(); self.search.setPlaceholderText("Поиск по имени/автору/описанию…")
        self.search.textChanged.connect(self._refilter)

        self.btn_install = QPushButton("📂 Установить");      self.btn_install.clicked.connect(self.upload_extension)
        self.btn_uninst  = QPushButton("🗑 Удалить…");         self.btn_uninst.clicked.connect(self.uninstall_extension)
        self.btn_reload  = QPushButton("🔁 Перезагрузить всё"); self.btn_reload.clicked.connect(self._reload_all)
        self.btn_folder  = QPushButton("📁 Папка расширений"); self.btn_folder.clicked.connect(lambda: _open_folder(self.extensions_dir))

        bar.addWidget(self.search, 1)
        bar.addWidget(self.btn_install)
        bar.addWidget(self.btn_uninst)
        bar.addWidget(self.btn_reload)
        bar.addWidget(self.btn_folder)
        root.addLayout(bar)

        # list
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.cards_host = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        # toast
        self._toast = QLabel(""); self._toast.setObjectName("Toast")
        self._toast.setVisible(False)
        root.addWidget(self._toast)

        # style
        self.setStyleSheet(self._qss())

        # data
        self._cards: List[ExtCard] = []
        self._load_and_render()

    # ------------------------------ styling ------------------------------
    def _qss(self) -> str:
        return """
        QWidget#ExtensionsManager { background:#0f1117; color:#e6edf3; }

        QLabel#Caption {
            font-size:18px; font-weight:700; color:#e6edf3;
            padding:4px 6px;
            border-bottom:2px solid qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #22d3ee, stop:1 #6E9CFF);
        }

        QLineEdit { background:#111827; border:1px solid #223046; border-radius:8px; padding:8px 10px; color:#e6edf3; }
        QLineEdit:focus {
            border:1px solid #3b82f6; background:#1a2232;
        }

        QPushButton { background:#111827; border:1px solid #223046; border-radius:8px; padding:8px 14px; color:#e6edf3; font-weight:500; }
        QPushButton:hover { background:#172131; border-color:#3b82f6; color:#dbe8ff; }
        QPushButton:pressed { background:#1b2434; }

        QToolButton { background:#111827; border:1px solid #223046; border-radius:8px; padding:6px; min-width:32px; min-height:32px; color:#e6edf3; }
        QToolButton:hover { background:#182234; border-color:#3b82f6; color:#dbe8ff; }

        QScrollArea { border:none; background:transparent; }

        QFrame#ExtCard { background:rgba(15,18,27,0.9); border:1px solid #1e293b; border-radius:12px; }

        QLabel#ExtTitle { font-weight:600; font-size:16px; color:#e6edf3; }
        QLabel#ExtMeta { font-size:12px; color:#8aa0b6; }
        QLabel#ExtDesc { font-size:13px; color:#b7c5d3; }

        QLabel#Toast { background: rgba(59,130,246,0.12); border:1px solid rgba(59,130,246,0.45); color:#cfe1ff; padding:6px 10px; border-radius:8px; font-weight:500; }

        QCheckBox { padding:4px; }

        QScrollBar:vertical { background:transparent; width:10px; margin:4px 0 4px 0; }
        QScrollBar::handle:vertical { background:#2b3a4e; border-radius:5px; min-height:24px; }
        QScrollBar::handle:vertical:hover { background:#375172; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QScrollBar:horizontal { height:0; }
        """

    # ------------------------------ loader wiring ------------------------------
    def _list_infos(self) -> List[ExtInfo]:
        infos: List[ExtInfo] = []
        try:
            if hasattr(self.loader, "list"):
                for e in self.loader.list():
                    name = getattr(e, "name", None) or str(e)
                    path = getattr(e, "path", os.path.join(self.extensions_dir, name))
                    enabled = bool(getattr(e, "enabled", True))
                    ver = desc = author = ""
                    mf = os.path.join(path, "manifest.json")
                    if os.path.isfile(mf):
                        try:
                            with open(mf, "r", encoding="utf-8") as f:
                                m = json.load(f)
                            ver = str(m.get("version", ""))
                            desc = str(m.get("description", ""))
                            author = str(m.get("author", ""))
                        except Exception:
                            pass
                    infos.append(ExtInfo(name, path, enabled, ver, desc, author))
                return infos
        except Exception:
            traceback.print_exc()

        # fallback: scan dir
        try:
            for entry in sorted(os.listdir(self.extensions_dir)):
                p = os.path.join(self.extensions_dir, entry)
                if not os.path.isdir(p):
                    continue
                enabled = True; ver = desc = author = ""
                mf = os.path.join(p, "manifest.json")
                if os.path.isfile(mf):
                    try:
                        with open(mf, "r", encoding="utf-8") as f:
                            m = json.load(f)
                        enabled = bool(m.get("enabled", True))
                        ver = m.get("version", "")
                        desc = m.get("description", "")
                        author = m.get("author", "")
                    except Exception:
                        pass
                infos.append(ExtInfo(entry, p, enabled, ver, desc, author))
        except Exception:
            traceback.print_exc()
        return infos

    def _enable_ext(self, name: str, enabled: bool) -> None:
        if hasattr(self.loader, "enable"):
            self.loader.enable(name, enabled)
        else:
            mf = os.path.join(self.extensions_dir, name, "manifest.json")
            try:
                m = json.load(open(mf, "r", encoding="utf-8")) if os.path.isfile(mf) else {}
                m["enabled"] = bool(enabled)
                json.dump(m, open(mf, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            except Exception:
                pass
        try:
            if hasattr(self.loader, "install_profile_scripts"):
                self.loader.install_profile_scripts()
        except Exception:
            pass

    def _reload_one(self, name: str) -> None:
        if hasattr(self.loader, "reload_extension"):
            self.loader.reload_extension(name)
        elif hasattr(self.loader, "reload"):
            self.loader.reload()
        elif hasattr(self.loader, "install_profile_scripts"):
            self.loader.install_profile_scripts()
        self.toast(f"Перезагружено: {name}")

    def _reload_all(self) -> None:
        try:
            if hasattr(self.loader, "reload"):
                self.loader.reload()
            elif hasattr(self.loader, "install_profile_scripts"):
                self.loader.install_profile_scripts()
            self.toast("Все расширения перезагружены")
        except Exception as e:
            self.toast(f"Ошибка перезагрузки: {e}")

    # ------------------------------ UI logic ------------------------------
    def _load_and_render(self) -> None:
        for i in reversed(range(self.cards_layout.count())):
            w = self.cards_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self._cards: List[ExtCard] = []
        for info in self._list_infos():
            card = ExtCard(info, self)
            self.cards_layout.addWidget(card)
            self._cards.append(card)
        self.cards_layout.addStretch(1)
        self._refilter()

    def _refilter(self) -> None:
        q = (self.search.text() or "").strip().lower()
        if not q:
            for c in self._cards:
                c.setVisible(True)
            return
        for c in self._cards:
            hay = " ".join([
                c.info.name.lower(),
                (c.info.author or "").lower(),
                (c.info.description or "").lower(),
                os.path.basename(c.info.path).lower()
            ])
            c.setVisible(q in hay)

    # ------------------------------ actions ------------------------------
    def upload_extension(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку расширения")
        if not folder:
            return
        name = os.path.basename(os.path.normpath(folder))
        target = os.path.join(self.extensions_dir, name)
        if os.path.exists(target):
            QMessageBox.warning(self, "Установка", "Такая папка уже существует.")
            return
        try:
            shutil.copytree(folder, target)
            self.toast(f"Установлено: {name}")
            self._reload_all(); self._load_and_render()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка установки", str(e))

    def uninstall_extension(self):
        visible = [c for c in self._cards if c.isVisible()]
        if not visible:
            QMessageBox.information(self, "Удаление", "Нет видимых расширений.")
            return
        names = [c.info.name for c in visible]
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "Удаление расширения", "Выберите расширение:", names, 0, False)
        if not ok or not name:
            return
        path = os.path.join(self.extensions_dir, name)
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Удаление", "Папка не найдена.")
            return
        if QMessageBox.question(self, "Подтверждение", f"Удалить '{name}' безвозвратно?") != QMessageBox.Yes:
            return
        try:
            shutil.rmtree(path)
            try:
                if hasattr(self.loader, "enabled_extensions"):
                    self.loader.enabled_extensions.pop(name, None)
                    if hasattr(self.loader, "_save_enabled_states"):
                        self.loader._save_enabled_states()
            except Exception:
                pass
            self.toast(f"Удалено: {name}")
            self._reload_all(); self._load_and_render()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка удаления", str(e))

    def show_extension_info(self, info: ExtInfo):
        """Новый стиль окна информации (диалог с вкладками)."""
        readme_path = os.path.join(info.path, "README.md")
        manifest_path = os.path.join(info.path, "manifest.json")
        manifest_text = ""; readme_text = ""
        if os.path.isfile(manifest_path):
            try:
                manifest_text = json.dumps(json.load(open(manifest_path, "r", encoding="utf-8")), ensure_ascii=False, indent=2)
            except Exception:
                try:
                    # если битый JSON — показываем как есть
                    manifest_text = open(manifest_path, "r", encoding="utf-8").read()
                except Exception:
                    manifest_text = "{}"
        if os.path.isfile(readme_path):
            try:
                readme_text = open(readme_path, "r", encoding="utf-8").read()
            except Exception:
                readme_text = ""

        dlg = ExtInfoDialog(info, manifest_text, readme_text, parent=self)
        dlg.exec_()

    # ------------------------------ toast ------------------------------
    def toast(self, text: str, ms: int = 1600):
        self._toast.setText(text); self._toast.setVisible(True)
        QTimer.singleShot(ms, lambda: self._toast.setVisible(False))
