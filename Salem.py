# ===== Стандартная библиотека =====
import os
import re
import sys
import ctypes
import subprocess
import weakref
from ctypes import wintypes
from ctypes.wintypes import HWND, DWORD, BOOL
from typing import Optional
from urllib.parse import quote, quote_plus, quote_plus
from pathlib import Path

# ===== PyQt5 =====
from PyQt5 import sip, QtSvg
from PyQt5.QtCore import (
    Qt, QUrl, QUrlQuery, QTimer, QEvent, QPoint,
    QThread, pyqtSignal, QEasingCurve, QPropertyAnimation, QRect, QSettings, QObject, QSize
)
from PyQt5.QtGui import (
    QDesktopServices, QMouseEvent, QKeySequence, QFont, QBrush,
    QFontDatabase, QPainter, QPen, QPixmap, QColor, QPalette,
    QIcon, QCursor
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QToolButton, QTabBar, QFrame, QShortcut, QGraphicsDropShadowEffect,
    QPushButton, QLineEdit, QLabel, QTabWidget, QComboBox,
    QListWidget, QProgressBar, QMessageBox, QFileDialog,
    QPlainTextEdit, QDockWidget, QMenu, QInputDialog, QTreeWidget, QTreeWidgetItem, QAction, QSizePolicy
)
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView, QWebEngineSettings, QWebEngineProfile,
    QWebEnginePage, QWebEngineDownloadItem, QWebEngineFullScreenRequest
)
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtMultimedia import QSoundEffect, QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget
from PyQt5.QtSvg import QSvgRenderer

# ===== Внешние библиотеки =====
from selenium.webdriver.common.proxy import Proxy, ProxyType
from google_auth_oauthlib.flow import InstalledAppFlow

# ===== Локальные модули =====
from modules.bookmarks import BookmarksBar
from modules.salem_sidebar import SettingsSidebar
from modules.mods_loader import ModLoader
from modules.mods_ui import ModManager
from modules.Optimizer import ResourceOptimizer
from modules.pip_native import PiPMediaWindow
from modules.AccountBridge import AccountBridge
from modules.downloads_ui import DownloadsPanel
from modules.extensions_ui import ExtensionManager
from modules.extensions_loader import ExtensionLoader
from modules.extensions_popup import ExtensionsMiniPopup
from modules.history_ui import HistoryPanel
from modules.pip_mode import PipWindow

from pathlib import Path
import sys, os, logging

def _env_path(key: str, default: Path) -> Path:
    p = os.environ.get(key)
    return Path(p).resolve() if p else default.resolve()

def _base_assets_root() -> Path:
    if os.environ.get("SALEM_ASSETS_ROOT"):
        return Path(os.environ["SALEM_ASSETS_ROOT"]).resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

def _assets_candidates() -> list[Path]:
    roots: list[Path] = []
    roots.append(_base_assets_root())
    mp = getattr(sys, "_MEIPASS", None)
    if mp:
        roots.append(Path(mp))
    roots.append(Path(__file__).resolve().parent)
    roots.append(Path(__file__).resolve().parent.parent)
    return roots

def _resolve_asset(*parts: str) -> str:
    sub = Path(*parts)
    if sub.is_absolute():
        return str(sub)

    rels = [sub]
    sp = str(sub).replace("\\", "/")
    if not (sp.startswith("img/") or sp.startswith("modules/") or sp.startswith("icons/")):
        rels += [Path("img") / sub, Path("img/icons") / sub, Path("modules/icons") / sub, Path("icons") / sub]

    def with_ext(p: Path):
        return [p] if p.suffix else [
            p.with_suffix(".svg"), p.with_suffix(".png"),
            p.with_suffix(".ico"), p.with_suffix(".gif")
        ]

    for root in _assets_candidates():
        for r in rels:
            for cand in with_ext(r):
                full = (root / cand)
                if full.exists():
                    return str(full)

    logging.getLogger("launcher").warning(
        "ASSET not found: %s  roots=%s", sub, [str(x) for x in _assets_candidates()]
    )
    return str(_assets_candidates()[0] / sub)

def _icon(name: str) -> str:
    return _resolve_asset("img", "icons", name)


# ─────────────────────────────────────────────────────────────────────────────
# QTWEBENGINE: корректная инициализация без перезаписи переменных лаунчера.
# Удалить в Salem.py строки вида:
#   os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ...
#   os.environ["QTWEBENGINEPROCESS_PATH"] = ...
# и вставить этот блок (расположить ДО первого создания QApplication/QWebEngineView).
# ─────────────────────────────────────────────────────────────────────────────
import os, sys, shutil, logging
from pathlib import Path

def _qt_candidates() -> list[Path]:
    roots: list[Path] = []
    # из лаунчера / окружения
    for k in ("SALEM_ASSETS_ROOT", "SALEM_RUNTIME_ROOT", "SALEM_RT", "SALEM_RT_ROOT"):
        v = os.environ.get(k)
        if v:
            p = Path(v)
            roots.extend([p, p / "_internal"])
    # _MEIPASS (onefile) и рядом с exe/скриптом
    exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    roots.extend([exe_dir, exe_dir.parent])
    meipass = Path(getattr(sys, "_MEIPASS", str(exe_dir)))
    if meipass not in roots:
        roots.append(meipass)
    # site-packages PyQt5 (как донор)
    roots.append(Path(sys.prefix) / "Lib" / "site-packages" / "PyQt5" / "Qt5")
    # PyInstaller temp donor (_MEI…)
    for k in ("PYI_MEIPASS2", "PYI_MEIPASS"):
        v = os.environ.get(k)
        if v:
            roots.append(Path(v))
    # dedup + resolve
    out: list[Path] = []
    for r in roots:
        try:
            rr = r.resolve()
            if rr not in out:
                out.append(rr)
        except Exception:
            pass
    return out

def _find_qt_rt_in(roots: list[Path]) -> Path | None:
    for r in roots:
        # Вариант: встроенный qt_runtime
        p = r / "qt_runtime" / "bin" / "QtWebEngineProcess.exe"
        if p.exists():
            return (r / "qt_runtime").resolve()
        # Варианты: сырой Qt5 layout
        for base in (r / "Qt5", r):
            p = base / "bin" / "QtWebEngineProcess.exe"
            if p.exists():
                return base.resolve()
    return None

def _copy_from_sitepackages_to(target_rt: Path) -> bool:
    """Минимальный перенос файлов из site-packages/PyQt5/Qt5 → target_rt."""
    site_rt = Path(sys.prefix) / "Lib" / "site-packages" / "PyQt5" / "Qt5"
    if not site_rt.exists():
        return False
    try:
        (target_rt / "bin").mkdir(parents=True, exist_ok=True)
        (target_rt / "plugins").mkdir(parents=True, exist_ok=True)
        (target_rt / "qml").mkdir(parents=True, exist_ok=True)
        (target_rt / "resources").mkdir(parents=True, exist_ok=True)
        (target_rt / "translations" / "qtwebengine_locales").mkdir(parents=True, exist_ok=True)

        # bin
        for name in ("QtWebEngineProcess.exe", "d3dcompiler_47.dll"):
            src = site_rt / "bin" / name
            if src.exists():
                shutil.copy2(src, target_rt / "bin" / name)

        # resources
        for name in (
            "icudtl.dat",
            "qtwebengine_resources.pak",
            "qtwebengine_resources_100p.pak",
            "qtwebengine_resources_200p.pak",
            "qtwebengine_devtools_resources.pak",
        ):
            src = site_rt / "resources" / name
            if src.exists():
                shutil.copy2(src, target_rt / "resources" / name)

        # locales
        loc_src = site_rt / "translations" / "qtwebengine_locales"
        if loc_src.exists():
            for f in loc_src.glob("*.pak"):
                shutil.copy2(f, target_rt / "translations" / "qtwebengine_locales" / f.name)
        return (target_rt / "bin" / "QtWebEngineProcess.exe").exists()
    except Exception:
        return False

def _configure_qt_runtime():
    log = logging.getLogger("launcher")
    qtp = os.environ.get("QTWEBENGINEPROCESS_PATH", "")
    if qtp and Path(qtp).is_file():
        rt = Path(qtp).resolve().parent.parent
        os.environ.setdefault("QT_PLUGIN_PATH", str(rt / "plugins"))
        os.environ.setdefault("QTWEBENGINE_LOCALES", str(rt / "translations" / "qtwebengine_locales"))
        os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", str(rt / "resources"))
    else:
        roots = _qt_candidates()
        rt = _find_qt_rt_in(roots)

        if rt is None:
            base = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
            target_rt = (base / "qt_runtime").resolve()
            if _copy_from_sitepackages_to(target_rt):
                rt = target_rt

        if rt is not None:
            os.environ["QTWEBENGINEPROCESS_PATH"] = str(rt / "bin" / "QtWebEngineProcess.exe")
            os.environ.setdefault("QT_PLUGIN_PATH", str(rt / "plugins"))
            os.environ.setdefault("QTWEBENGINE_LOCALES", str(rt / "translations" / "qtwebengine_locales"))
            os.environ.setdefault("QTWEBENGINE_RESOURCES_PATH", str(rt / "resources"))

    os.environ.setdefault("QTWEBENGINE_REMOTE_DEBUGGING", "0")
    os.environ.setdefault("QT_LOGGING_RULES", "qt.webenginecontext.debug=false;qt.qpa.*=false")

_configure_qt_runtime()

flags = set((os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS") or "").split())
flags |= {
    "--enable-gpu",
    "--ignore-gpu-blocklist",
    "--enable-gpu-rasterization",
    "--enable-zero-copy",
    "--enable-oop-rasterization",
    "--enable-accelerated-video-decode",
}
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(sorted(flags))



from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QGraphicsBlurEffect
)

# --- WinAPI структура для сообщений ---
class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd",    wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam",  wintypes.WPARAM),
        ("lParam",  wintypes.LPARAM),
        ("time",    wintypes.DWORD),
        ("pt",      wintypes.POINT),
    ]

WM_NCHITTEST   = 0x0084
HTNOWHERE      = 0
HTCLIENT       = 1
HTCAPTION      = 2
HTLEFT         = 10
HTRIGHT        = 11
HTTOP          = 12
HTTOPLEFT      = 13
HTTOPRIGHT     = 14
HTBOTTOM       = 15
HTBOTTOMLEFT   = 16
HTBOTTOMRIGHT  = 17

class MainWindow(QWidget):
    """Кастомная шапка окна с кнопками управления и рабочим контекстным меню."""

    RESIZE_MARGIN = 8  # зона «ловли» ресайза в пикселях

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        # Не затеняем QObject.parent(), используем свой хэндл на главное окно
        self._win: QWidget = parent
        self.setWindowTitle("Salem Corp. Browser 4.5")
        self.setWindowIcon(QIcon(_resolve_asset("img/icon2.ico")))

        self.is_dark = True
        self._is_max = False
        self._drag_pos: Optional[QPoint] = None
        self._resizing: bool = False
        self._resize_dir: Optional[str] = None
        self._start_geom: Optional[QRect] = None

        self.setMouseTracking(True)
        self.setFixedHeight(42)
        # Шапка — это дочерний виджет, НЕ отдельное окно
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Единый стиль
        self.setStyleSheet(
            """
            background: #23272e;
            border-bottom: 1px solid #44475a;
            """
        )

        # Контекстное меню через CustomContextMenu + страховка в mousePressEvent

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch(1)

        # Кнопки
        self.btn_min = QPushButton("—")
        self.btn_max = QPushButton("▢")
        self.btn_close = QPushButton("✕")
        self.btn_theme = QPushButton("◓")

        for btn in (self.btn_min, self.btn_max, self.btn_close, self.btn_theme):
            btn.setFixedSize(39, 30)
            btn.setStyleSheet(
                """
                QPushButton { background: none; color: #42fff7; border: none; font-size: 28px; }
                QPushButton:hover { background: #35384a; }
                """
            )

        # Сигналы
        self.btn_min.clicked.connect(self._win.showMinimized)
        self.btn_max.clicked.connect(self.toggle_max_restore)
        self.btn_close.clicked.connect(self._win.close)
        self.btn_theme.clicked.connect(self.toggle_theme)

        layout.addWidget(self.btn_theme)
        layout.addWidget(self.btn_min)
        layout.addWidget(self.btn_max)
        layout.addWidget(self.btn_close)


    # ---------- Тема ----------
    def toggle_theme(self):
        self.is_dark = not self.is_dark
        if hasattr(self._win, "apply_global_theme"):
            self._win.apply_global_theme(self.is_dark)

    def set_global_theme(self, is_dark: bool):
        palette = QPalette()
        if is_dark:
            palette.setColor(QPalette.Window, QColor("#23272e"))
            palette.setColor(QPalette.WindowText, QColor("#eaeaea"))
            palette.setColor(QPalette.Base, QColor("#181b22"))
            palette.setColor(QPalette.AlternateBase, QColor("#282a36"))
            palette.setColor(QPalette.Text, QColor("#f8f8f2"))
            palette.setColor(QPalette.Button, QColor("#282a36"))
            palette.setColor(QPalette.ButtonText, QColor("#42fff7"))
            palette.setColor(QPalette.Highlight, QColor("#068ce6"))
            palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
            try:
                palette.setColor(QPalette.PlaceholderText, QColor("#9aa4b2"))
            except Exception:
                pass
        else:
            palette.setColor(QPalette.Window, QColor("#f8fafc"))
            palette.setColor(QPalette.WindowText, QColor("#23272e"))
            palette.setColor(QPalette.Base, QColor("#ffffff"))
            palette.setColor(QPalette.AlternateBase, QColor("#eaeaea"))
            palette.setColor(QPalette.Text, QColor("#23272e"))
            palette.setColor(QPalette.Button, QColor("#e0e7ef"))
            palette.setColor(QPalette.ButtonText, QColor("#068ce6"))
            palette.setColor(QPalette.Highlight, QColor("#42fff7"))
            palette.setColor(QPalette.HighlightedText, QColor("#181b22"))
            try:
                palette.setColor(QPalette.PlaceholderText, QColor("#6b7280"))
            except Exception:
                pass

        QApplication.instance().setPalette(palette)
        QApplication.instance().setStyleSheet(self.global_stylesheet(is_dark))

    def global_stylesheet(self, dark: bool) -> str:
        if dark:
            return (
                """
                QWidget[role="navbar"] { background-color: #141414; border-bottom: 1px solid #2b2b2b; padding: 8px 0; }
                QLineEdit { background-color: #1a1a1a; color: #f2f2f2; border: 2px solid #ff0057; border-radius: 12px; padding: 10px 16px; min-height: 42px; font-size: 17px; selection-background-color: #ff0057; selection-color: #ffffff; }
                QLineEdit:hover { border: 2px solid #ff3399; background-color: #1f1f1f; }
                QLineEdit:focus { border: 2px solid #ff66c4; background-color: #222222; }
                QPushButton { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #2c003e, stop:1 #1a001f); color: #ff1f8f; border: 1.5px solid #ff3399; border-radius: 10px; font-size: 16px; padding: 6px 12px; min-height: 34px; margin: 0 3px; font-weight: 600; }
                QPushButton:hover { background-color: #ff1f8f; color: #ffffff; border: 1.5px solid #ff66c4; }
                QPushButton:pressed { background-color: #290022; color: #ff66c4; border: 1.5px solid #ff3399; }
                QTabBar::tab { background-color: #1a001f; color: #e0e0e0; border-top-left-radius: 12px; border-top-right-radius: 12px; padding: 8px 18px; font-weight: 600; font-size: 15px; margin-top: 2px; }
                QTabBar::tab:selected { background-color: #2c003e; color: #ff1f8f; border: 1px solid #ff3399; }
                QTabWidget::pane { border-top: 2px solid #ff1f8f; }
                QListWidget { background-color: #141414; color: #f2f2f2; border: 1px solid #2b2b2b; border-radius: 6px; font-size: 14px; }
                QMenu { background-color: #1a1a1a; color: #f2f2f2; border: 1px solid #2b2b2b; font-size: 14px; }
                QMenu::item:selected { background-color: #ff1f8f; color: #ffffff; }
                """
            )
        else:
            return (
                """
                QWidget[role="navbar"] { background-color: #f3f4f6; border-bottom: 1px solid #d1d5db; padding: 8px 0; }
                QLineEdit { background-color: #ffffff; color: #111827; border: 2px solid #3b82f6; border-radius: 12px; padding: 10px 16px; min-height: 42px; font-size: 17px; selection-background-color: #3b82f6; selection-color: #ffffff; }
                QLineEdit:hover { border: 2px solid #60a5fa; background-color: #ffffff; }
                QLineEdit:focus { border: 2px solid #93c5fd; background-color: #ffffff; }
                QPushButton { background-color: #e5e7eb; color: #111827; border: 1.5px solid #cbd5e1; border-radius: 10px; font-size: 16px; padding: 6px 12px; min-height: 34px; font-weight: 600; }
                QPushButton:hover { background-color: #dbeafe; border-color: #93c5fd; }
                QPushButton:pressed { background-color: #c7d2fe; border-color: #93c5fd; }
                QTabBar::tab { background-color: #eef2ff; color: #111827; border-top-left-radius: 12px; border-top-right-radius: 12px; padding: 8px 18px; font-weight: 600; font-size: 15px; margin-top: 2px; }
                QTabBar::tab:selected { background-color: #dbeafe; color: #1d4ed8; border: 1px solid #93c5fd; }
                QTabWidget::pane { border-top: 2px solid #93c5fd; }
                QListWidget { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; border-radius: 6px; font-size: 14px; }
                QMenu { background-color: #ffffff; color: #111827; border: 1px solid #d1d5db; font-size: 14px; }
                QMenu::item:selected { background-color: #3b82f6; color: #ffffff; }
                """
            )
        
    def _teardown_webengine(self):
        try:
            # Отключаем DevTools от ВСЕХ страниц
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                try:
                    w.page().setDevToolsPage(None)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # Гарантируем удаление страниц/вью после закрытия вкладок
            for i in range(self.tabs.count()-1, -1, -1):
                w = self.tabs.widget(i)
                try:
                    self.tabs.removeTab(i)
                except Exception:
                    pass
                try:
                    page = w.page()
                    if page:
                        page.deleteLater()
                except Exception:
                    pass
                try:
                    w.deleteLater()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            # И уже после этого — профиль
            if getattr(self, 'profile', None):
                self.profile.deleteLater()
        except Exception:
            pass

    # ---------- Управление окном ----------
    def toggle_max_restore(self):
        if self._is_max:
            self._win.showNormal()
        else:
            self._win.showMaximized()
        self._is_max = not self._is_max

    # ---------- Обработчики мыши (drag/resize + вызов меню) ----------
    def mousePressEvent(self, e: QMouseEvent):
        # Правый клик — вызвать меню вручную (страховка против хит‑теста)
        if e.button() == Qt.RightButton:
            self.show_titlebar_menu(self.mapFromGlobal(e.globalPos()))
            return

        # Если попали на кнопку — не перехватываем
        widget = self.childAt(e.pos())
        if isinstance(widget, QPushButton):
            super().mousePressEvent(e)
            return

        pos = e.pos()
        margin = self.RESIZE_MARGIN
        rect = self.rect()
        x, y = pos.x(), pos.y()

        left = x <= margin
        right = x >= rect.width() - margin
        top = y <= margin
        bottom = y >= rect.height() - margin

        if e.button() == Qt.LeftButton:
            if top and left:
                self._resize_dir = "top_left"
            elif top and right:
                self._resize_dir = "top_right"
            elif bottom and left:
                self._resize_dir = "bottom_left"
            elif bottom and right:
                self._resize_dir = "bottom_right"
            elif left:
                self._resize_dir = "left"
            elif right:
                self._resize_dir = "right"
            elif top:
                self._resize_dir = "top"
            elif bottom:
                self._resize_dir = "bottom"
            else:
                self._resize_dir = None

            if self._resize_dir:
                self._resizing = True
                self._drag_pos = e.globalPos()
                self._start_geom = self._win.geometry()
                return

            # Перетаскивание окна
            self._drag_pos = e.globalPos() - self._win.frameGeometry().topLeft()

        super().mousePressEvent(e)

    def mouseMoveEvent(self, e: QMouseEvent):
        # Курсоры и обработка drag/resize
        widget = self.childAt(e.pos())
        if isinstance(widget, QPushButton):
            self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(e)
            return

        pos = e.pos()
        margin = self.RESIZE_MARGIN
        rect = self.rect()
        x, y = pos.x(), pos.y()

        if self._resizing and self._drag_pos is not None:
            self._perform_resize(e.globalPos())
            return

        left = x <= margin
        right = x >= rect.width() - margin
        top = y <= margin
        bottom = y >= rect.height() - margin

        if top and left:
            cursor = Qt.SizeFDiagCursor
        elif top and right:
            cursor = Qt.SizeBDiagCursor
        elif bottom and left:
            cursor = Qt.SizeBDiagCursor
        elif bottom and right:
            cursor = Qt.SizeFDiagCursor
        elif left:
            cursor = Qt.SizeHorCursor
        elif right:
            cursor = Qt.SizeHorCursor
        elif top:
            cursor = Qt.SizeVerCursor
        elif bottom:
            cursor = Qt.SizeVerCursor
        else:
            cursor = Qt.ArrowCursor

        self.setCursor(QCursor(cursor))

        # Перемещение окна
        if self._drag_pos and not self._resizing and e.buttons() == Qt.LeftButton:
            self._win.move(e.globalPos() - self._drag_pos)

        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e: QMouseEvent):
        self._resizing = False
        self._resize_dir = None
        self._drag_pos = None
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)

        # Snap‑логика — если есть у главного окна
        try:
            if hasattr(self._win, "try_edge_snap"):
                QTimer.singleShot(0, self._win.try_edge_snap)
        except Exception:
            pass

    # ---------- Ресайз ----------
    def _perform_resize(self, global_pos: QPoint):
        diff = global_pos - self._drag_pos
        geom = self._start_geom

        left = geom.left()
        top = geom.top()
        right = geom.right()
        bottom = geom.bottom()

        min_width = self._win.minimumWidth() or 200
        min_height = self._win.minimumHeight() or 150

        if "left" in self._resize_dir:
            new_left = left + diff.x()
            if new_left < right - min_width:
                left = new_left
        if "right" in self._resize_dir:
            new_right = right + diff.x()
            if new_right > left + min_width:
                right = new_right
        if "top" in self._resize_dir:
            new_top = top + diff.y()
            if new_top < bottom - min_height:
                top = new_top
        if "bottom" in self._resize_dir:
            new_bottom = bottom + diff.y()
            if new_bottom > top + min_height:
                bottom = new_bottom

        self._win.setGeometry(left, top, right - left, bottom - top)

    # ---------- Пример пункта меню PiP ----------
    def menu_pip_mode(self):
        try:
            if hasattr(self, "pip_window") and self.pip_window and self.pip_window.isVisible():
                self.pip_window.close()
                self.pip_window = None
            else:
                self.pip_window = PipWindow(self)
                # позиционируем относительно главного окна
                geo = self._win.geometry()
                self.pip_window.move(geo.right() - 500, geo.top() + 80)
                self.pip_window.show()
        except Exception as e:
            print("[PiP] Ошибка:", e)

from PyQt5.QtGui import QMovie

class AnimatedTabBar(QTabBar):
    newTabRequested = pyqtSignal()
    contextActionRequested = pyqtSignal(str, int)  # action, index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SalemTabBar")
        self.setContentsMargins(0, 0, 0, 0)
        self.setElideMode(Qt.ElideRight)
        self.setExpanding(False)
        self.setMovable(True)
        self.setTabsClosable(True)
        self.setUsesScrollButtons(True)
        self.setDrawBase(False)

        self._ih = self._indicator_height()
        self._indicator = QFrame(self)
        self._indicator.setObjectName("tabIndicator")
        self._indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._indicator.lower()
        self._indicator.resize(0, self._ih)

        self._anim = QPropertyAnimation(self._indicator, b"geometry", self)
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        # акцент/свечение
        self._accent = QColor("#22d3ee")
        self._glow = QGraphicsDropShadowEffect(self._indicator)
        self._glow.setColor(self._accent)
        self._glow.setBlurRadius(18)
        self._glow.setOffset(0, 0)
        self._indicator.setGraphicsEffect(self._glow)
        self._glow_enabled = True
        self._glow_strength = 0.6

        # аудиосостояния
        self._audible = {}  # idx->bool
        self._muted   = {}  # idx->bool

        # ─────────────────────────────────────────────────────────────
        #   LOADING SPINNER (GIF)
        # ─────────────────────────────────────────────────────────────
        self._spinner_path = None
        self._spinner_size = 16  # px (будет auto-scale под HiDPI)
        self._spinner_movie = None  # QMovie, общий для всех вкладок
        self._loading_tabs = set()  # индексы, где показываем спиннер
        self._saved_icons = {}      # idx -> QIcon (восстанавливаем после загрузки)

        # следим за перетаскиваниями/удалениями, чтобы не сломать индексы
        try:
            self.tabMoved.connect(self._on_tab_moved)
        except Exception:
            pass

        self.setStyleSheet("""
            QTabBar { margin:0; padding:0; border:0; }
            QTabBar::tab {
                margin:0; padding:6px 10px; border:0; border-radius:8px;
            }
            QTabBar::tab:selected { background: rgba(255,255,255,0.05); }
            QTabBar::tab:hover    { background: rgba(255,255,255,0.03); }
            QTabBar::close-button { margin-left:6px; }
            #tabIndicator { background: #22d3ee; border-radius: 2px; }
        """)
        self.currentChanged.connect(self.animate_to)

    # ——— PUBLIC API: индикатор загрузки ———
    def set_loading_gif(self, path: str, size: int = 16):
        """Указать .gif для спиннера и его целевой размер (px)."""
        self._spinner_path = path or None
        self._spinner_size = max(8, int(size))
        self._setup_movie()

    def set_tab_loading(self, index: int, loading: bool):
        """Включить/выключить спиннер на конкретной вкладке."""
        if not (0 <= index < self.count()):
            return
        if loading:
            if index not in self._loading_tabs:
                # сохраним текущий favicon и временно уберём его, чтобы не перекрывался спиннером
                self._saved_icons[index] = self.tabIcon(index)
                self.setTabIcon(index, QIcon())
                self._loading_tabs.add(index)
                self._setup_movie()
                if self._spinner_movie and self._spinner_movie.state() != QMovie.Running:
                    self._spinner_movie.start()
            self.update(self.tabRect(index))
        else:
            if index in self._loading_tabs:
                self._loading_tabs.discard(index)
                # вернём favicon
                if index in self._saved_icons:
                    try:
                        self.setTabIcon(index, self._saved_icons.pop(index))
                    except Exception:
                        self._saved_icons.pop(index, None)
                self.update(self.tabRect(index))
                # если не осталось загрузок — остановим анимацию
                if self._spinner_movie and not self._loading_tabs:
                    self._spinner_movie.stop()

    # ——— API для браузера ———
    def set_indicator_color(self, hex_color: str):
        c = QColor(hex_color) if hex_color else QColor()
        if not c.isValid(): return
        self._accent = c
        rad = max(1, self._ih // 2)
        self._indicator.setStyleSheet(f"#tabIndicator {{ background: {c.name()}; border-radius: {rad}px; }}")
        self._glow.setColor(self._accent); self._update_glow()

    def set_indicator_glow(self, enabled=True, radius=18, strength=0.6):
        self._glow_enabled = bool(enabled)
        self._glow.setBlurRadius(max(0, int(radius)))
        self._glow_strength = max(0.0, min(1.0, float(strength)))
        self._update_glow()

    def set_tab_audio_state(self, index: int, audible: bool, muted: bool = None):
        if 0 <= index < self.count():
            self._audible[index] = bool(audible)
            if muted is not None:
                self._muted[index] = bool(muted)
            self.update(self.tabRect(index))

    def set_tab_muted(self, index: int, muted: bool):
        if 0 <= index < self.count():
            self._muted[index] = bool(muted)
            self.update(self.tabRect(index))

    # ——— геометрия/анимация ———
    def _indicator_height(self) -> int:
        return max(2, int(2 * max(1.0, self.devicePixelRatioF())))

    def _target_rect(self, index: int) -> QRect:
        h = self.height(); y = h - self._ih
        if not (0 <= index < self.count()): return QRect(0, y, 0, self._ih)
        r = self.tabRect(index)
        x = max(0, min(r.x() + 8, self.width() - max(12, r.width()-16)))
        w = max(12, r.width() - 16)
        return QRect(x, y, w, self._ih)

    def _jump_to(self, index: int):
        self._indicator.setGeometry(self._target_rect(index))

    def animate_to(self, index: int):
        new_h = self._indicator_height()
        if new_h != self._ih:
            self._ih = new_h
            self._indicator.resize(self._indicator.width(), self._ih)
            self.set_indicator_color(self._accent.name())
        self._anim.stop()
        self._anim.setStartValue(self._indicator.geometry())
        self._anim.setEndValue(self._target_rect(index))
        self._anim.start()
        self._update_glow()

    def _update_glow(self):
        a = int(255 * (self._glow_strength if self._glow_enabled else 0))
        col = QColor(self._accent); col.setAlpha(a)
        self._glow.setEnabled(self._glow_enabled and self.currentIndex() >= 0)
        self._glow.setColor(col)

    # ——— служебные события ———
    def changeEvent(self, ev):
        if ev.type() in (QEvent.FontChange, QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange):
            self._ih = self._indicator_height(); self._jump_to(self.currentIndex()); self._update_glow()
        return super().changeEvent(ev)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._jump_to(self.currentIndex())

    def tabInserted(self, index):
        super().tabInserted(index)
        self._jump_to(self.currentIndex())

    def tabRemoved(self, index):
        super().tabRemoved(index)
        # зачистим возможные хвосты загрузки
        self._loading_tabs.discard(index)
        self._saved_icons.pop(index, None)
        # сдвинем маппинги справа от удалённого
        self._reindex_maps_after_remove(index)
        self._jump_to(min(self.currentIndex(), self.count()-1))

    # ——— рисуем 🔊 маркер и GIF-спиннер ———
    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing, True)

        # 1) GIF-спиннер для вкладок, что грузятся
        if self._spinner_movie and self._loading_tabs:
            frame = self._spinner_movie.currentPixmap()
            if not frame.isNull():
                sz = int(round(self._spinner_size * max(1.0, self.devicePixelRatioF())))
                pm = frame.scaled(sz, sz, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                for i in list(self._loading_tabs):
                    if not (0 <= i < self.count()):
                        continue
                    r = self.tabRect(i)
                    if r.isNull():
                        continue
                    # позиционируем слева (где обычно favicon)
                    x = int(r.left() + 8)
                    y = int(r.center().y() - pm.height() / (2 * pm.devicePixelRatio()))
                    p.drawPixmap(x, y, pm)


        # 2) аудио-маркеры
        for i in range(self.count()):
            r = self.tabRect(i)
            if r.isNull(): continue
            audible = bool(self._audible.get(i, False))
            muted   = bool(self._muted.get(i, False))
            if not audible and not muted: continue
            d, pad = 7, 6
            cx = r.right() - pad - d//2
            cy = r.top() + pad + d//2
            color = QColor(self._accent); color.setAlpha(120 if muted else 220)
            p.setBrush(QBrush(color)); p.setPen(Qt.NoPen)
            p.drawEllipse(QPoint(cx, cy), d//2, d//2)
            if muted:
                pen = QPen(QColor("#000000")); pen.setWidth(2); pen.setCosmetic(True); p.setPen(pen)
                p.drawLine(cx - d//2, cy + d//2, cx + d//2, cy - d//2)

        p.end()

    # ─────────────────────────────────────────────────────────────
    #   Вспомогательное для GIF
    # ─────────────────────────────────────────────────────────────
    def _setup_movie(self):
        """Ленивая инициализация QMovie, автообновление TabBar по кадрам."""
        if self._spinner_movie:
            if self._spinner_path:
                # заменить файл спиннера на лету
                self._spinner_movie.stop()
                self._spinner_movie.deleteLater()
                self._spinner_movie = None
            else:
                return
        # Попытка найти спиннер по умолчанию, если путь не задан
        path = self._spinner_path or self._guess_default_spinner()
        if not path:
            return
        self._spinner_movie = QMovie(path, parent=self)
        # если GIF не валиден — ничего не рисуем
        if not self._spinner_movie.isValid():
            self._spinner_movie = None
            return
        self._spinner_movie.setCacheMode(QMovie.CacheAll)
        # обновляем отрисовку на каждый кадр
        self._spinner_movie.frameChanged.connect(lambda _=None: (self._loading_tabs and self.update()))
        if self._loading_tabs:
            self._spinner_movie.start()

    def _guess_default_spinner(self) -> str:
        """Поиск дефолтного спиннера в ассетах проекта."""
        # подставь свои пути, если у тебя другой каталог
        candidates = [
            "img/icons/loader.gif",
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
        return ""

    def _on_tab_moved(self, fr: int, to: int):
        """Корректируем индексы для состояний загрузки/иконок при перетаскивании."""
        def remap_index(i: int) -> int:
            if i == fr:
                return to
            if fr < to and fr < i <= to:
                return i - 1
            if fr > to and to <= i < fr:
                return i + 1
            return i

        self._loading_tabs = { remap_index(i) for i in self._loading_tabs }
        self._saved_icons = { remap_index(i): ic for i, ic in list(self._saved_icons.items()) }

    def _reindex_maps_after_remove(self, removed: int):
        """Сдвигаем хранилища индексов после удаления вкладки."""
        new_loading = set()
        for i in list(self._loading_tabs):
            if i < removed:
                new_loading.add(i)
            elif i > removed:
                new_loading.add(i - 1)
        self._loading_tabs = new_loading

        new_icons = {}
        for i, ic in list(self._saved_icons.items()):
            if i < removed:
                new_icons[i] = ic
            elif i > removed:
                new_icons[i - 1] = ic
        self._saved_icons = new_icons



from PyQt5.QtWidgets import QDockWidget

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDockWidget, QWidget, QVBoxLayout
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile


class _QuietDevToolsPage(QWebEnginePage):
    """Suppresses noisy DevTools console messages (Protocol Error, devtools:// spam)."""
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        src = str(sourceID or "")
        msg = str(message or "")
        if src.startswith("devtools://") or "Protocol Error" in msg:
            return
        try:
            super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
        except Exception:
            pass


class DevToolsDock(QDockWidget):
    """
    Drop‑in replacement for your DevTools dock.

    Key changes vs current impl:
      • Uses devtoolsPage.setInspectedPage(page) (stable across QtWebEngine versions)
        instead of page.setDevToolsPage(devtoolsPage).
      • Keeps a single persistent DevTools QWebEnginePage bound to a profile you pass in
        (or defaultProfile). Reattaches on tab change.
      • Provides detach() on hide/close to avoid stale bindings and blank pages later.
      • Safe layout container, no stylesheet hassles.
    """

    def __init__(self, main_window, profile: QWebEngineProfile = None):
        super().__init__("DevTools 45.01 build Salem-Explorer", main_window)
        self.setObjectName("DevToolsDock")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable
        )

        # Create a dedicated DevTools view/page (quiet page to reduce console noise)
        self.view = QWebEngineView(self)
        self._profile = profile or QWebEngineProfile.defaultProfile()
        self._dev_page = _QuietDevToolsPage(self._profile, self.view)
        self.view.setPage(self._dev_page)

        container = QWidget(self)
        lay = QVBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.view)
        self.setWidget(container)

        self._inspected = None  # type: QWebEnginePage | None
        self.hide()

    # внутри класса DevToolsDock

    def attach_to(self, target):
        """Прикрепить DevTools к странице. Принимает QWebEnginePage ИЛИ QWebEngineView."""
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage
        except Exception:
            QWebEngineView = QWebEnginePage = None

        page = None
        if QWebEnginePage and isinstance(target, QWebEnginePage):
            page = target
        elif QWebEngineView and isinstance(target, QWebEngineView):
            page = target.page()
        if page is None:
            return

        try:
            # новый API
            if self._inspected and self._inspected is not page:
                try: self._dev_page.setInspectedPage(None)
                except Exception: pass
            self._dev_page.setInspectedPage(page)
            self._inspected = page
        except Exception:
            # старый API
            try:
                page.setDevToolsPage(self._dev_page)
                self._inspected = page
            except Exception:
                pass

    def attach(self, view_or_page):
        """Совместимость со старыми вызовами: self.devtools.attach(view)."""
        self.attach_to(view_or_page)


    def show_for(self, page: QWebEnginePage):
        self.attach_to(page)
        self.show()
        self.raise_()

    def toggle_for(self, page: QWebEnginePage, force: bool = False):
        if force or not self.isVisible():
            self.show_for(page)
        else:
            self.hide()

    # ——— lifecycle ———
    def closeEvent(self, e):
        # Ensure we unhook to prevent stale bindings that can blank the dock next time
        try:
            self.detach()
        except Exception:
            pass
        super().closeEvent(e)

    def hideEvent(self, e):
        # Keep the devtools page alive but detach from inspected page
        try:
            self.detach()
        except Exception:
            pass
        super().hideEvent(e)


class SalemPage(QWebEnginePage):
    """
    Кастомная страница: перехватываем mailto:, можно расширять дальше
    (tel:, sms:, intent:, и т.п.).
    """
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        # Перехват кликов/редиректов вида mailto:...
        if url.scheme().lower() == "mailto":
            # Передадим главному окну — как обрабатывать (системно, Gmail, свой composer)
            w = self.window()
            if hasattr(w, "handle_mailto_url"):
                w.handle_mailto_url(url)
            else:
                # На всякий случай — по умолчанию системный почтовик
                QDesktopServices.openUrl(url)
            return False  # НЕ грузим mailto в webview
        return super().acceptNavigationRequest(url, _type, isMainFrame)

    def createWindow(self, windowType):
        # Попросим главное окно создать новую вкладку и вернуть страницу
        w = self.window()
        if hasattr(w, "_create_popup_page"):
            return w._create_popup_page(windowType) 


# --- Async worker для сканирования расширений ---
from PyQt5.QtCore import QObject, QThread, pyqtSignal

class _ExtScanWorker(QObject):
    finished = pyqtSignal(object)   # payload: список/словарь расширений или None
    error    = pyqtSignal(str)

    def __init__(self, loader):
        super().__init__()
        self._loader = loader

    def run(self):
        try:
            # максимально щадяще к диску
            list_fn = getattr(self._loader, "list_extensions", None) or getattr(self._loader, "scan", None)
            data = list_fn() if callable(list_fn) else None
            self.finished.emit(data)
        except Exception as e:
            self.error.emit(str(e))
            self.finished.emit(None)



class SalemBrowser(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Базовые параметры окна
        self.setWindowTitle("Salem Corp. Browser 4.5")
        self.setWindowIcon(QIcon(_resolve_asset("img/icons/icon.ico")))
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setMouseTracking(True)
        self.setGeometry(50, 50, 1300, 670)
        self.apply_global_theme(True)

        # ── Профиль и WebEngine: ПЕРЕХОД НА ДЕФОЛТНЫЙ ПРОФИЛЬ
        #    Было: self.profile = QWebEngineProfile("SalemProfile", QApplication.instance())
        #    Стало: один общий defaultProfile для всего приложения.
        self.profile = QWebEngineProfile.defaultProfile()
        self._tune_webengine_fastpath(self.profile)

        # Не задаём кастомные пути для defaultProfile (они глобальны и могут быть уже зафиксированы).
        # Если очень хочешь хранить всё рядом с приложением — можно оставить ПОЛИТИКИ и лимиты:
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
        self.profile.setHttpCacheMaximumSize(512 * 1024 * 1024)  # 512MB

        # ── Служебные поля
        self.extension_manager_window = None
        self.history_panel = None
        self.current_webview = None
        self._page_to_view = {}
        self._icon_buttons = []
        self._forced_theme = None
        self.pip_window = None
        self.ext_popup = None
        self.chatgpt_dock = None
        self.RESIZE_MARGIN = 8

        # mailto режимы
        self.mailto_mode = "smart"
        self.mailto_fallback = "gmail"
        self.mailto_compose_url = "http://127.0.0.1:5000/compose"

        # домашняя/поиск
        self.home_url = "http://127.0.0.1:5000/"
        self.search_engine = "google"
        self.search_custom = ""
        self.mute_background = True

        # ── DevTools (используем тот же defaultProfile)
        try:
            self.devtools = DevToolsDock(self, self.profile)
            self.addDockWidget(Qt.RightDockWidgetArea, self.devtools)
            self._install_devtools_shortcuts()
        except Exception:
            self.devtools = None

        # ── Расширения
        ext_dir = os.environ.get("SALEM_EXT")
        if not ext_dir:
            ext_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "extensions")
        self.extension_loader = ExtensionLoader(extensions_dir=ext_dir, profile=self.profile)
        self.extension_loader.install_profile_scripts()

        # ── Моды
        mods_dir = os.environ.get("SALEM_MODS")
        if not mods_dir:
            mods_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mods")
        self.mod_loader = ModLoader(mods_dir=mods_dir, profile=self.profile)


        # ── Хоткеи
        self.setup_hotkeys()

        # ── Кастомная заголовочная панель
        self.titlebar = MainWindow(self)

        # ── Вкладки
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setTabBarAutoHide(False)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)
        self.tabs.currentChanged.connect(self.current_tab_changed)  # один раз

        DEFAULT_TAB_TITLE = "Новая вкладка"


        bar = AnimatedTabBar(self.tabs)
        self.tabs.setTabBar(bar)
        bar.set_loading_gif(self._asset("img/icons/loader.gif"), size=18)

        self._init_tab_context_menu()

        # История/первая вкладка
        self._ensure_history_panel()
        self.init_tab_ui()

        # ── Навигационная панель
        nav_bar = QWidget()
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(10, 4, 10, 4)
        nav_layout.setSpacing(6)

        back_btn    = self.create_icon_button(_icon("circle-arrow-left.svg"),  self.navigate_back,    "← Назад / Артқа  (Alt+←)")
        forward_btn = self.create_icon_button(_icon("circle-arrow-right.svg"), self.navigate_forward, "→ Вперёд / Алға  (Alt+→)")
        refresh_btn = self.create_icon_button(_icon("refresh.svg"),            self.refresh_page,     "Обновить / Жаңарту (F5, Ctrl+R)")
        home_btn    = self.create_icon_button(_icon("home.svg"),               self.navigate_home,    "Домой / Басты бет (Alt+Home)")

        for b in (back_btn, forward_btn, refresh_btn, home_btn):
            nav_layout.addWidget(b)

        self.url_bar = QLineEdit()
        self.url_bar.returnPressed.connect(self._on_urlbar_enter)
        self.url_bar.setPlaceholderText("URL мекенжай енгізіңіз...")
        self.url_bar.setFixedHeight(40)
        self.url_bar.setMinimumWidth(320)
        nav_layout.addWidget(self.url_bar, 1)

        new_tab_btn      = self.create_icon_button(_icon("new-tab.svg"),      self.add_new_tab,            "Новая вкладка / Жаңа бет (Ctrl+T)")
        user_account_btn = self.create_icon_button(_icon("user.svg"),         self.enable_user_account,    "Аккаунт (Ctrl+Shift+U)")
        menu_btn         = self.create_icon_button(_icon("menu.svg"),         self.open_menu,              "Меню / Мәзір (Alt+M)")
        open_file_btn    = self.create_icon_button(_icon("folder.svg"),       self.open_file,              "Открыть файл / Файл ашу (Ctrl+O)")
        devtools_btn     = self.create_icon_button(_icon("app-window.svg"),   self.open_devtools_tab,      "DevTools (F12, Ctrl+Shift+I)")
        self.extensions_btn = self.create_icon_button(_icon("puzzle.svg"),    self.open_extensions_window, "Расширения / Кеңейтімдер (Ctrl+Shift+E)")
        downloads_btn    = self.create_icon_button(_icon("download.svg"),     self.open_downloads_tab,     "Загрузки / Жүктемелер (Ctrl+J)")
        history_btn      = self.create_icon_button(_icon("history.svg"),      self.open_history_tab,       "История / Тарих (Ctrl+H)")
        pip_btn          = self.create_icon_button(_icon("pip.svg"),          self.menu_pip_mode,          "Picture-in-Picture (PiP)")

        for b in (new_tab_btn, user_account_btn, menu_btn, open_file_btn, devtools_btn,
                  self.extensions_btn, downloads_btn, history_btn, pip_btn):
            nav_layout.addWidget(b)

        self.apply_navbar_theme()
        nav_bar.setProperty("role", "navbar")

        # ── Центральный layout
        central_widget = QWidget(self)
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        self.main_layout = central_layout

        # Верх: заголовок и навбар
        self.main_layout.addWidget(self.titlebar)
        self.main_layout.addWidget(nav_bar)

        # Панель закладок
        self.bookmarks_bar = BookmarksBar(
            self,
            icon_size=QSize(18, 18),
            asset_resolver=getattr(self, "_asset", None),
            current_view_resolver=lambda: self.tabs.currentWidget()
        )
        self.bookmarks_bar.openRequested.connect(lambda url, title: self.add_new_tab(url, title))
        self.main_layout.insertWidget(2, self.bookmarks_bar)

        # Хоткеи для закладок
        QShortcut(QKeySequence("Ctrl+D"), self,
                  lambda: self.bookmarks_bar.add_from_view(self.tabs.currentWidget()))
        QShortcut(QKeySequence("Ctrl+Shift+B"), self, self.bookmarks_bar.toggle)

        # Вкладки под панелью закладок
        self.main_layout.addWidget(self.tabs)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.tabs.setMinimumSize(640, 360)
        self.tabs.currentChanged.connect(lambda _=None: self._fix_tab_content_sizing())
        QTimer.singleShot(0, lambda: self._fix_tab_content_sizing())

        # ── Settings Sidebar
        anchor = self._active_tab_container() or central_widget
        self.settings_panel = SettingsSidebar(anchor, asset_resolver=getattr(self, "_asset", None))
        self.settings_panel.set_profile(self.profile)
        self.settings_panel.settingsChanged.connect(self.apply_settings_from_sidebar)
        self.settings_panel.closed.connect(
            lambda: (self.tabs.currentWidget().setFocus()
                     if isinstance(self.tabs.currentWidget(), QWebEngineView) else None)
        )
        self.sidebar = self.settings_panel
        self.tabs.currentChanged.connect(
            lambda idx: self.settings_panel.set_anchor(self._active_tab_container() or central_widget)
        )

        # ── Центр в окно
        self.setCentralWidget(central_widget)

        # ── UA и прочие веб-настройки
        self.set_user_agent()

        # ── Optimizer: теперь прямо с defaultProfile
        if not hasattr(self, "optimizer"):
            self.optimizer = ResourceOptimizer(
                browser=self,
                profile=self.profile,
                interval_ms=20_000,
                cpu_limit=60,
                ram_limit=75,
                discard_aggressive=False,
                cache_cleanup_each=6
            )
            # безопасное подключение, если в Optimizer нет on_tab_activated
            cb = getattr(self.optimizer, "on_tab_activated", None)
            if callable(cb):
                self.tabs.currentChanged.connect(cb)
            else:
                self.tabs.currentChanged.connect(self._activate_current_tab_resources)

        # ── Отложенная реполировка — когда все виджеты уже на месте
        QTimer.singleShot(0, lambda: self._schedule_repolish(
            self,
            getattr(self, "tabs", None),
            getattr(self, "titlebar", None),
            getattr(self, "url_bar", None)
        ))

    def set_user_agent(self):
        # Chrome 128 desktop UA (update version here when needed)
        ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0.6613.137 Safari/537.36"
        )


        prof = getattr(self, "profile", None) or QWebEngineProfile.defaultProfile()
        try:
            prof.setHttpUserAgent(ua)
        except Exception:
            pass


        # Prefer Russian, then English — reduces CAPTCHA chances
        try:
            prof.setHttpAcceptLanguage("ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7") # Qt ≥5.12
        except Exception:
            pass


        # Re-apply to already opened pages (if any were created earlier)
        try:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                v = w if hasattr(w, "page") else w.findChild(QWebEngineView)
                if v:
                    try:
                        v.page().profile().setHttpUserAgent(ua)
                    except Exception:
                        pass
        except Exception:
            pass

    def _fix_tab_content_sizing(self, widget=None):
        """Make sure the webview inside a tab expands and has a sane minimum size."""
        try:
            w = widget or self.tabs.currentWidget()
            v = w if isinstance(w, QWebEngineView) else (w.findChild(QWebEngineView) if w else None)
            if v:
                v.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                v.setMinimumSize(460, 360)
                try:
                    v.setZoomFactor(1.0)
                except Exception:
                    pass
        except Exception:
            pass

    def _asset(self, *parts: str) -> str:
        from pathlib import Path
        import os, sys, logging

        if len(parts) == 1 and isinstance(parts[0], str) and (":" in parts[0] or parts[0].startswith(("/", "\\"))):
            return parts[0]

        subpath = Path(*parts) if parts else Path("")
        if subpath.is_absolute():
            return str(subpath)

        roots = []
        try:
            roots.append(Path(sys.executable).parent if getattr(sys, "frozen", False)
                         else Path(os.path.abspath(sys.argv[0])).parent)
        except Exception:
            pass
        mp = getattr(sys, "_MEIPASS", None)
        if mp:
            roots.append(Path(mp))
        here = Path(__file__).resolve().parent
        roots.append(here)
        roots.append(here.parent)

        variants = [subpath]
        sp = str(subpath).replace("\\", "/")
        if not (sp.startswith("img/") or sp.startswith("modules/") or sp.startswith("icons/")):
            variants += [Path("img") / subpath, Path("img/icons") / subpath, Path("modules/icons") / subpath, Path("icons") / subpath]

        def _with_exts(p: Path):
            return [p] if p.suffix else [p.with_suffix(".svg"), p.with_suffix(".png"), p.with_suffix(".gif"), p.with_suffix(".ico")]

        for v in variants:
            for r in roots:
                for cand in _with_exts(v):
                    full = r / cand
                    if full.exists():
                        return str(full)

        logging.getLogger("launcher").warning("ASSET not found: %s  roots=%s", str(subpath), [str(x) for x in roots])
        return str(roots[0] / subpath) if roots else str(subpath)


    def _init_tab_context_menu(self):
        """Подключает ПКМ-меню на таб-бар, если tabs существует."""
        tabs = getattr(self, "tabs", None)
        if isinstance(tabs, QTabWidget):
            bar = tabs.tabBar()
            if isinstance(bar, QTabBar):
                bar.setContextMenuPolicy(Qt.CustomContextMenu)
                # UniqueConnection, чтобы не задвоить при повторном вызове
                try:
                    bar.customContextMenuRequested.disconnect()
                except Exception:
                    pass
                bar.customContextMenuRequested.connect(self._show_tab_context_menu)

    def _show_tab_context_menu(self, pos):
        tabs = self.tabs
        bar  = tabs.tabBar()
        index = bar.tabAt(pos)
        if index < 0:
            return

        w = tabs.widget(index)
        # состояние звука
        is_muted = False
        try:
            is_muted = bool(w.page().isAudioMuted())
        except Exception:
            pass
        # закреплена ли вкладка
        data = tabs.tabBar().tabData(index)
        pinned = (data is True) or (data == "pinned") or (isinstance(data, dict) and data.get("pinned", False))


        menu = QMenu(self)

        # Новая вкладка
        a_new = QAction("Новая вкладка", self)
        a_new.triggered.connect(lambda: self._open_blank_tab())
        menu.addAction(a_new)

        # Обновить
        a_reload = QAction("Обновить вкладку", self)
        a_reload.triggered.connect(lambda: self._reload_tab(index))
        menu.addAction(a_reload)

        # Звук
        a_mute = QAction(("Включить" if is_muted else "Отключить") + " звук вкладки", self)
        a_mute.triggered.connect(lambda: self._toggle_mute_tab(index))
        menu.addAction(a_mute)

        # Закрепить
        a_pin = QAction(("Открепить" if pinned else "Закрепить") + " вкладку", self)
        a_pin.triggered.connect(lambda: self._toggle_pin_tab(index))
        menu.addAction(a_pin)

        # Дублировать
        a_dup = QAction("Дублировать вкладку", self)
        a_dup.triggered.connect(lambda: self._duplicate_tab(index))
        menu.addAction(a_dup)

        # В закладки
        a_bm = QAction("Добавить вкладку в закладки", self)
        a_bm.triggered.connect(lambda: self._bookmark_tab(index))
        menu.addAction(a_bm)

        menu.exec_(bar.mapToGlobal(pos))

    # ── ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ (в этом же классе) ─────────────────────────
    def _open_blank_tab(self):
        # поддержка обеих сигнатур add_new_tab
        try:
            self.add_new_tab()                      # без аргументов
        except TypeError:
            from PyQt5.QtCore import QUrl
            self.add_new_tab(QUrl("about:blank"), "Новая вкладка")

    def _reload_tab(self, index: int):
        try:
            w = self.tabs.widget(index)
            if hasattr(w, "reload"):
                w.reload()
            elif hasattr(w, "page"):
                w.page().triggerAction(w.page().Reload)
        except Exception:
            pass

    def _toggle_mute_tab(self, index: int):
        try:
            w = self.tabs.widget(index)
            pg = w.page()
            pg.setAudioMuted(not pg.isAudioMuted())
        except Exception:
            pass

    def _toggle_pin_tab(self, index: int):
        bar = self.tabs.tabBar()
        if index < 0:
            return
        data = bar.tabData(index)
        pinned = (data is True) or (data == "pinned") or (isinstance(data, dict) and data.get("pinned", False))

        new_state = not pinned
        # единый формат хранения
        bar.setTabData(index, {"pinned": new_state})

        # визуал
        try:
            self.tabs.setTabTextColor(
                index,
                Qt.yellow if new_state else self.palette().windowText().color()
            )
        except Exception:
            pass


    def _duplicate_tab(self, index: int):
        try:
            w = self.tabs.widget(index)
            url = None
            if hasattr(w, "url"):
                url = w.url()
            elif hasattr(w, "page") and hasattr(w.page(), "url"):
                url = w.page().url()
            if url:
                # поддержка обеих сигнатур add_new_tab
                try:
                    self.add_new_tab(url)
                except TypeError:
                    self.add_new_tab(url, self.tabs.tabText(index))
        except Exception:
            pass

    def _bookmark_tab(self, index: int):
        try:
            w = self.tabs.widget(index)
            title = self.tabs.tabText(index)
            url = None
            if hasattr(w, "url"):
                u = w.url()
                url = u.toString() if hasattr(u, "toString") else str(u)
            elif hasattr(w, "page") and hasattr(w.page(), "url"):
                u = w.page().url()
                url = u.toString() if hasattr(u, "toString") else str(u)
            if not url:
                return
            # если есть менеджер закладок
            if callable(getattr(self, "add_bookmark", None)):
                self.add_bookmark(url, title)
            elif getattr(self, "bookmarks_bar", None) and callable(getattr(self.bookmarks_bar, "add_bookmark", None)):
                self.bookmarks_bar.add_bookmark(url, title)
            else:
                print("[bookmarks] add:", title, url)
        except Exception:
            pass

    def _tune_webengine_fastpath(self, profile: QWebEngineProfile):
        from PyQt5.QtWebEngineWidgets import QWebEngineSettings
        gs = QWebEngineSettings.globalSettings()


        # Графика/канвас/видео
        try: gs.setAttribute(QWebEngineSettings.WebGLEnabled, True)
        except: pass
        try: gs.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
        except: pass
        try: gs.setAttribute(QWebEngineSettings.FocusOnNavigationEnabled, True)
        except: pass
        try: gs.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)
        except: pass


        # Контент
        try: gs.setAttribute(QWebEngineSettings.AutoLoadImages, True)
        except: pass
        try: gs.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        except: pass
        try: gs.setAttribute(QWebEngineSettings.PluginsEnabled, False)
        except: pass

        gs = QWebEngineSettings.globalSettings()
        try: gs.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)  # попапы отдаем в createWindow, меньше костылей
        except: pass
        try: gs.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, True)  # не автозапускать видео
        except: pass
        try: gs.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)  # встроенная страница ошибок дешевле, чем кастомные редиректы
        except: pass

        # Хедеры/UA – уже есть свой user‑agent, оставляем как есть


        # Безопасные GPU‑флаги Chromium (Windows)
        flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
        wanted = [
            "--enable-gpu",
            "--ignore-gpu-blocklist",
            "--enable-gpu-rasterization",
            "--enable-zero-copy",
        ]
        for f in wanted:
            if f not in flags:
                flags += (" " + f)
        os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()

    
    def nativeEvent(self, eventType, message):
        if eventType != "windows_generic_MSG":
            return False, 0
    
        msg = MSG.from_address(int(message))
    
        if msg.message == WM_NCHITTEST and not self.isMaximized():
            gp = QPoint(int(msg.pt.x), int(msg.pt.y))
            p  = self.mapFromGlobal(gp)
    
            x, y = p.x(), p.y()
            w, h = self.width(), self.height()
            m = getattr(self, "RESIZE_MARGIN", 8)
    
            # Ресайз по краям/углам
            if x <= m and y <= m:           return True, HTTOPLEFT
            if x >= w - m and y <= m:       return True, HTTOPRIGHT
            if x <= m and y >= h - m:       return True, HTBOTTOMLEFT
            if x >= w - m and y >= h - m:   return True, HTBOTTOMRIGHT
            if x <= m:                      return True, HTLEFT
            if x >= w - m:                  return True, HTRIGHT
            if y <= m:                      return True, HTTOP
            if y >= h - m:                  return True, HTBOTTOM
    
            # Пустая зона в кастомной шапке — перетаскивание окна
            try:
                if self.titlebar and self.titlebar.geometry().contains(p):
                    lp = self.titlebar.mapFromGlobal(gp)
                    w_under = self.titlebar.childAt(lp)
                    from PyQt5.QtWidgets import QPushButton
                    if isinstance(w_under, QPushButton):
                        return True, HTCLIENT   # клики по кнопкам — обычный клиент
                    return True, HTCAPTION      # иначе тянем окно
            except Exception:
                pass
            
            return True, HTCLIENT
    
        return False, 0
    
    def _install_devtools_shortcuts(self):
        """Устанавливает хоткеи для открытия/закрытия DevTools."""
        QShortcut(QKeySequence("F12"), self,
        activated=lambda: self.devtools.toggle_for(self._current_page()))
        QShortcut(QKeySequence("Ctrl+Shift+I"), self,
        activated=lambda: self.devtools.toggle_for(self._current_page(), force=True))


    def _current_webview(self):
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            w = self.tabs.currentWidget()
            return w if isinstance(w, QWebEngineView) else None
        except Exception:
            return None


    def _current_page(self):
        v = self._current_webview()
        return v.page() if v else None


    def open_devtools_tab(self):
        page = self._current_page()
        if page:
            self.devtools.toggle_for(page, force=True)

    def _wire_view(self, view: QWebEngineView):
        """Подключаем сигналы/DevTools и т.п. в одном месте."""
        try:
            view.loadStarted.connect(lambda: self._on_load_started(view))
            view.loadProgress.connect(lambda p: self._on_load_progress(view, p))
            view.loadFinished.connect(lambda ok: self._on_load_finished(view, ok))
        except Exception:
            pass
        # если есть модуль DevTools — цепляем тут
        try:
            self.devtools.attach(view)
        except Exception:
            pass

    def _create_popup_page(self, windowType):
        """Создать новую вкладку под pop-up/target=_blank/window.open."""
        view = QWebEngineView(self)
        page = SalemPage(self.profile, view) if hasattr(self, "profile") else SalemPage(parent=view)
        view.setPage(page)
        self._wire_view(view)
        idx = self.tabs.addTab(view, "Жаңа бет")
        self.tabs.setCurrentIndex(idx)
        return page


    
    def _find_extensions_tab(self):
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), ExtensionManager):
                return i
        return -1

    def open_extensions_manager_tab(self):
        """Открыть/переключиться на вкладку 'Расширения'."""
        idx = self._find_extensions_tab()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
            return

        w = ExtensionManager(self.extension_loader, parent=self, as_page=True)
        i = self.tabs.addTab(w, "Расширения")
        self.tabs.setCurrentIndex(i)
    
    def _on_sidebar_settings(self, data: dict):
        """
        Сайдбар прислал изменения настроек: акцент/шрифт/и пр.
        Применяем глобально и затем даём сайдбару перекрыть локальным QSS (для SVG-иконок).
        """
        accent = data.get("accent_color")
        self._accent = data.get("accent_color", getattr(self, "_accent", "#22d3ee"))
        self._ui_font = data.get("ui_font", getattr(self, "_ui_font", "Segoe UI"))

        # Текущая тема из app/window property
        app = QApplication.instance()
        is_dark = (app.property("theme") == "dark") or (self.property("theme") == "dark")

        # 1) Глобальная тема и лист (учтут новый _accent, если global_stylesheet его использует)
        self.apply_global_theme(bool(is_dark))

        # 2) Сохраним акцент в настройки и обновим таб-бар
        if accent:
            QSettings("SalemCorp", "SalemExplorer").setValue("accent_color", accent)
            try:
                bar = self.tabs.tabBar()
            except Exception:
                bar = None
            if bar:
                if hasattr(bar, "set_indicator_color"):
                    try:
                        bar.set_indicator_color(accent)
                    except Exception:
                        pass
                else:
                    bar.setStyleSheet(f"""
                        QTabBar::tab {{ padding: 6px 10px; }}
                        QTabBar::tab:selected {{ border-bottom: 2px solid {accent}; }}
                    """)

        # 3) Дадим сайдбару перекинуть СВОЙ QSS ПОСЛЕ глобального — это критично для перекраски SVG
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.apply_theme_from_anchor()
        except Exception:
            pass

        # 4) Лёгкая переполировка ключевых контейнеров
        for w in (self, self.tabs, getattr(self, 'titlebar', None), getattr(self, 'url_bar', None)):
            if w:
                w.style().unpolish(w); w.style().polish(w)


    def apply_settings_from_sidebar(self, cfg: dict):
        """
        Применение конфигурации из сайдбара (тема/акцент/шрифты/прочее).
        Гарантируем порядок: сначала глобальная тема, затем локальный QSS сайдбара.
        """
        app = QApplication.instance()

        # --- Тема ---
        theme = cfg.get('theme', 'system')
        if theme == 'dark':
            app.setProperty("theme", "dark"); self.setProperty("theme", "dark")
            self.apply_global_theme(True)
        elif theme == 'light':
            app.setProperty("theme", "light"); self.setProperty("theme", "light")
            self.apply_global_theme(False)
        else:
            # system → оставляем как есть; если не знаем — дефолтим на dark
            current_dark = (app.property("theme") == "dark") or (self.property("theme") == "dark") or True
            app.setProperty("theme", "dark" if current_dark else "light")
            self.setProperty("theme", "dark" if current_dark else "light")
            self.apply_global_theme(bool(current_dark))

        # --- Прочие настройки ---
        self.home_url = cfg.get('home_url') or "http://127.0.0.1:5000/"
        self.search_engine = cfg.get('search_engine', 'google')
        self.search_custom = cfg.get('search_custom', '')

        if hasattr(self, "downloads_panel"):
            try:
                self.downloads_panel.set_downloads_dir(cfg.get('downloads_dir') or "")
            except Exception as e:
                print("[settings] downloads dir apply failed:", e)

        if hasattr(QWebEngineSettings, 'PlaybackRequiresUserGesture'):
            QWebEngineSettings.globalSettings().setAttribute(
                QWebEngineSettings.PlaybackRequiresUserGesture,
                bool(cfg.get('require_gesture', False))
            )
        self.mute_background = bool(cfg.get('mute_background', True))

        # --- Акцент (весь UI) ---
        accent_hex = cfg.get('accent_color')
        if accent_hex:
            self._apply_accent_color(accent_hex)
            QSettings("SalemCorp", "SalemExplorer").setValue("accent_color", accent_hex)
            self._accent = accent_hex  # чтобы global_stylesheet при следующей сборке знал акцент

        # --- Шрифты (UI + web-контент) ---
        ui_font = cfg.get('ui_font') or QSettings("SalemCorp", "SalemExplorer").value("ui_font", "Segoe UI")
        if ui_font:
            self._apply_ui_font(ui_font)
            self._apply_web_fonts(ui_font)
            self._ui_font = ui_font

        # --- Сайдбар / фичи ---
        show_sidebar = bool(cfg.get('show_sidebar', True))
        if hasattr(self, "settings_panel"):
            if self.settings_panel.isVisible() and not show_sidebar:
                self.settings_panel.hide()

        self.force_dark = bool(cfg.get('force_dark', False))
        self._apply_force_dark_to_all_tabs(self.force_dark)

        if hasattr(self, "settings_panel") and hasattr(self.settings_panel, "btn_exit"):
            try:
                self.settings_panel.btn_exit.setVisible(True)
            except Exception as e:
                print("[settings] btn_exit apply failed:", e)

        # --- ВАЖНО: локальный QSS сайдбара поверх глобального (для SVG перекраски) ---
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.apply_theme_from_anchor()
        except Exception:
            pass

        # Лёгкая переполировка
        for w in (self, self.tabs, getattr(self, 'titlebar', None), getattr(self, 'url_bar', None)):
            if w:
                w.style().unpolish(w); w.style().polish(w)


    def _apply_accent_color(self, hex_color: str):
        """
        Акцент в палитре и мягкая переполировка. Сайдбар перекинет свой QSS после глобального.
        """
        try:
            color = QColor(hex_color)
            # обновим палитру окна (и, по желанию, приложения)
            app = QApplication.instance()
            pal = app.palette() if app else self.palette()
            pal.setColor(QPalette.Highlight, color)
            pal.setColor(QPalette.ButtonText, color)  # пусть кнопки/иконки подсветятся
            if app:
                app.setPalette(pal)
            self.setPalette(pal)
        except Exception:
            pass

        # Обновим стили навбара/таба (если у тебя есть такая функция)
        try:
            self.apply_navbar_theme()
        except Exception:
            pass

        # Полировка базовых контейнеров
        for w in (self, self.tabs, getattr(self, 'titlebar', None)):
            if w:
                w.style().unpolish(w); w.style().polish(w)

        # Дадим сайдбару перекинуть локальный QSS (важно для SVG цветовых токенов)
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.apply_theme_from_anchor()
        except Exception:
            pass


    def _apply_ui_font(self, family: str):
        app = QApplication.instance()
        if app:
            app.setFont(QFont(family))
        for w in (self, self.tabs, getattr(self, 'titlebar', None), getattr(self, 'url_bar', None)):
            if w:
                w.setFont(QFont(family))
                w.style().unpolish(w); w.style().polish(w)
        # Сайдбар тоже переложит QSS, если зависит от font tokens
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.apply_theme_from_anchor()
        except Exception:
            pass


    def _apply_web_fonts(self, family: str):
        roles = []
        for name in ("StandardFont","SansSerifFont","SerifFont","FixedFont","CursiveFont","FantasyFont"):
            if hasattr(QWebEngineSettings, name):
                roles.append(getattr(QWebEngineSettings, name))

        gs = QWebEngineSettings.globalSettings()
        for r in roles:
            try: gs.setFontFamily(r, family)
            except Exception: pass

        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, QWebEngineView):
                s = w.settings()
                for r in roles:
                    try: s.setFontFamily(r, family)
                    except Exception: pass
                try: w.page().setBackgroundColor(w.page().backgroundColor())
                except Exception: pass

    def _apply_force_dark_to_all_tabs(self, enable: bool):
        js_on  = "(() => { try { document.documentElement.style.colorScheme='dark'; } catch(e){} })();"
        js_off = "(() => { try { document.documentElement.style.colorScheme=''; } catch(e){} })();"
        for i in range(self.tabs.count()):
            w = self.tabs.widget(i)
            if isinstance(w, QWebEngineView):
                try: w.page().runJavaScript(js_on if enable else js_off)
                except Exception: pass


    def safe_exit(self):
        """Аккуратный завершатель: пауза/стоп медиа, выгрузка WebEngine-ресурсов,
        сворачивание DevTools/ PiP и тихий выход приложения.
        """
        if getattr(self, "_exiting", False):
            return
        self._exiting = True

        try:
            # вернуть view из PiP (если был)
            try:
                if hasattr(self, "_restore_from_pip"):
                    self._restore_from_pip()
            except Exception:
                pass

            # закрыть DevTools и отвязать от страниц
            try:
                if getattr(self, "devtools", None):
                    self.devtools.hide()
                    for i in range(self.tabs.count()):
                        w = self.tabs.widget(i)
                        from PyQt5.QtWebEngineWidgets import QWebEngineView
                        if isinstance(w, QWebEngineView):
                            try:
                                w.page().setDevToolsPage(None)
                            except Exception:
                                pass
            except Exception:
                pass

            # остановка медиаконтента и утилизация страниц
            try:
                from PyQt5.QtWebEngineWidgets import QWebEngineView
                for i in range(self.tabs.count() - 1, -1, -1):
                    w = self.tabs.widget(i)
                    if isinstance(w, QWebEngineView):
                        # мгновенно глушим и стопим страницу
                        try: self._stop_media_in(w)
                        except Exception: pass
                    # удаляем вкладку и dispose
                    try: self.tabs.removeTab(i)
                    except Exception: pass
                    try: self._dispose_view(w)
                    except Exception: pass
            except Exception:
                pass

            # корректно завершить расширения (если у лоадера есть метод)
            try:
                if hasattr(self, "extension_loader") and hasattr(self.extension_loader, "shutdown"):
                    self.extension_loader.shutdown()
            except Exception:
                pass

            # немного времени на очистку очереди событий — и выходим
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(60, QApplication.instance().quit)

        except Exception:
            # на крайний случай — принудительный выход
            QApplication.instance().quit()



    
    def _active_tab_container(self):
        """Возвращает виджет-контейнер текущей вкладки (fallback — centralWidget)."""
        tabs = getattr(self, "tabs", None) or getattr(self, "tabWidget", None)
        if tabs and hasattr(tabs, "currentWidget") and tabs.currentWidget():
            return tabs.currentWidget()
        return self.centralWidget()

    # внутри класса SalemBrowser
    def _stop_media_in(self, view):
        """Остановить любое воспроизведение в заданном QWebEngineView и корректно отпустить ресурсы."""
        from PyQt5.QtWebEngineWidgets import QWebEnginePage
        try:
            if not isinstance(view, QWebEngineView):
                return
            page = view.page()
            # 1) мгновенно глушим звук
            try:
                page.setAudioMuted(True)
            except Exception:
                pass
            # 2) останавливаем любые загрузки/воспроизведение страницей
            try:
                page.triggerAction(QWebEnginePage.Stop)
            except Exception:
                pass
            # 3) на всякий случай — пауза тегов видео/аудио (подходит для YouTube-плееров и прочих)
            try:
                page.runJavaScript("""
                    (function(){
                        try{
                            document.querySelectorAll('video,audio').forEach(function(m){
                                try{ m.pause(); }catch(e){}
                                try{ m.currentTime = 0; }catch(e){}
                                try{ m.src=''; m.removeAttribute('src'); }catch(e){}
                                try{ m.load(); }catch(e){}
                            });
                        }catch(e){}
                    })();
                """)
            except Exception:
                pass
            # 4) обрываем devtools-привязку к этой странице (если было)
            try:
                page.setDevToolsPage(None)
            except Exception:
                pass
        except Exception as e:
            print("[media-stop] error:", e)

    # уже есть подключение: self.tabs.tabCloseRequested.connect(self.close_current_tab)
    def close_current_tab(self, index: int):
        try:
            view = self.tabs.widget(index)
            # ВАЖНО: сначала глушим всё
            self._stop_media_in(view)
            # Удаляем из TabWidget
            self.tabs.removeTab(index)
            # Безопасно удаляем объекты (отпустит процессы/ресурсы движка)
            if isinstance(view, QWebEngineView):
                page = view.page()
                try:
                    view.setParent(None)
                except Exception:
                    pass
                try:
                    if page:
                        page.deleteLater()
                except Exception:
                    pass
                try:
                    view.deleteLater()
                except Exception:
                    pass
        except Exception as e:
            print("[tabs] close_current_tab failed:", e)
            
    def closeEvent(self, e):
        # вернуть view из PiP (у тебя это уже есть)
        try:
            self._restore_from_pip()
        except Exception:
            pass

        # пройтись по всем вкладкам и заглушить
        try:
            for i in range(self.tabs.count()):
                w = self.tabs.widget(i)
                self._stop_media_in(w)
        except Exception:
            pass

        super().closeEvent(e)



    
    # ───────────────────────────── helpers: assets ─────────────────────────────
    def _asset(self, rel_path: str) -> str:
        """Корректно находим ресурс в dev и в собранном exe."""
        base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        return os.path.join(base, rel_path.replace("/", os.sep))
    
    # ───────────────────────────── palette & theme ─────────────────────────────
    def _palette_is_dark(self) -> bool:
        c = self.palette().window().color()
        # простая lightness-эвристика
        lightness = (max(c.red(), c.green(), c.blue()) + min(c.red(), c.green(), c.blue())) / 510.0
        return lightness < 0.5
    
    def _global_is_dark(self) -> bool:
        # приоритет: принудительный режим → свойство окна → свойство приложения → эвристика по палитре
        if getattr(self, "_forced_theme", None) == "dark":
            return True
        if getattr(self, "_forced_theme", None) == "light":
            return False
        app = QApplication.instance()
        if app and app.property("theme") in ("dark", "light"):
            return app.property("theme") == "dark"
        if self.property("theme") in ("dark", "light"):
            return self.property("theme") == "dark"
        return self._palette_is_dark()
    
    def _icon_colors(self):
        """
        Возвращает кортеж (base, hover, active, disabled) как QColor.
        active использует акцент, если он задан (self._accent).
        """
        from PyQt5.QtGui import QColor
        dark = self._global_is_dark()
        accent = getattr(self, "_accent", "#22d3ee")
        base = QColor("#E8EAED" if dark else "#1f2937")
        hover = QColor("#FFFFFF" if dark else "#0b1220")
        active = QColor(accent)  # чек/актив — акцент
        disabled = QColor("#a6b0c3" if dark else "#475569")
        return base, hover, active, disabled
    
    # ───────────────────────── SVG → tinted QPixmap with cache ─────────────────
    def _icon_cache_key(self, path: str, color: QColor, size: QSize, dpr: float) -> tuple:
        return (os.path.abspath(path), color.rgba(), size.width(), size.height(), round(dpr, 2))
    
    def _make_tinted_icon(self, path: str, color: QColor, icon_size: QSize) -> QIcon:
        """
        Если SVG — рендерим в QPixmap и красим через CompositionMode_SourceIn.
        Если не SVG — отдаем как есть (PNG/ICO не перекрашиваем).
        Возвращаем QIcon с единственным pixmap (Normal/Off).
        """
        from PyQt5.QtSvg import QSvgRenderer
        from PyQt5.QtGui import QPixmap, QPainter, QIcon, QColor
        from PyQt5.QtCore import Qt, QRectF
    
        if not path.lower().endswith(".svg"):
            return QIcon(path)
    
        # HiDPI
        win = self.window().windowHandle() if self.window() else None
        dpr = win.devicePixelRatio() if (win and hasattr(win, "devicePixelRatio")) else 1.0
        w = max(1, int(icon_size.width()  * dpr))
        h = max(1, int(icon_size.height() * dpr))
    
        # кэш
        if not hasattr(self, "_icon_pix_cache"):
            self._icon_pix_cache = {}
        key = self._icon_cache_key(path, color, icon_size, dpr)
        pm = self._icon_pix_cache.get(key)
        if pm is None:
            pm = QPixmap(w, h)
            pm.fill(Qt.transparent)
            renderer = QSvgRenderer(path)
            painter = QPainter(pm)
            # рисуем исходный svg
            renderer.render(painter, QRectF(0, 0, w, h))
            # заливаем цветом поверх альфы
            painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
            painter.fillRect(pm.rect(), color)
            painter.end()
            pm.setDevicePixelRatio(dpr)
            self._icon_pix_cache[key] = pm
    
        icon = QIcon()
        icon.addPixmap(pm, QIcon.Normal, QIcon.Off)
        return icon
    
    def _compose_stateful_icon(self, path: str, base: QColor, hover: QColor, active: QColor, disabled: QColor, icon_size: QSize) -> QIcon:
        """
        Собирает QIcon с наборами состояний:
          Normal/Off  -> base
          Active/Off  -> hover (наведение)
          Selected/On -> active (checked)
          Disabled    -> disabled
        """
        icon = QIcon()
        # Normal
        icon.addPixmap(self._make_tinted_icon(path, base, icon_size).pixmap(icon_size),     QIcon.Normal,   QIcon.Off)
        # Hover (Qt использует Active для наведённых кнопок)
        icon.addPixmap(self._make_tinted_icon(path, hover, icon_size).pixmap(icon_size),    QIcon.Active,   QIcon.Off)
        icon.addPixmap(self._make_tinted_icon(path, hover, icon_size).pixmap(icon_size),    QIcon.Selected, QIcon.Off)
        # Checked (Selected/On)
        icon.addPixmap(self._make_tinted_icon(path, active, icon_size).pixmap(icon_size),   QIcon.Normal,   QIcon.On)
        icon.addPixmap(self._make_tinted_icon(path, active, icon_size).pixmap(icon_size),   QIcon.Active,   QIcon.On)
        icon.addPixmap(self._make_tinted_icon(path, active, icon_size).pixmap(icon_size),   QIcon.Selected, QIcon.On)
        # Disabled
        icon.addPixmap(self._make_tinted_icon(path, disabled, icon_size).pixmap(icon_size), QIcon.Disabled, QIcon.Off)
        icon.addPixmap(self._make_tinted_icon(path, disabled, icon_size).pixmap(icon_size), QIcon.Disabled, QIcon.On)
        return icon
    
    # ─────────────────────────── create & apply theme ──────────────────────────
    def create_icon_button(
        self,
        icon_rel_path: str,
        callback,
        tooltip: str = "",
        btn_size: QSize = QSize(32, 32),
        icon_size: QSize = QSize(18, 18),
    ):
        from PyQt5.QtWidgets import QToolButton
        if not hasattr(self, "_icon_buttons"):
            self._icon_buttons = []
        if not hasattr(self, "_forced_theme"):
            self._forced_theme = None
    
        btn = QToolButton(self)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setFixedSize(btn_size)
        btn.setIconSize(icon_size)
        if tooltip:
            btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
    
        full_path = self._asset(icon_rel_path)
        self._icon_buttons.append((btn, full_path, btn_size, icon_size))
    
        # первичная установка набора иконок по текущей теме
        base, hover, active, disabled = self._icon_colors()
        btn.setIcon(self._compose_stateful_icon(full_path, base, hover, active, disabled, icon_size))
        return btn
    
    def apply_navbar_theme(self, mode: str = None):
        """
        mode: 'dark'|'light'|None(авто)
        Перекрасить все зарегистрированные иконки по глобальной теме и акценту.
        """
        self._forced_theme = mode  # запомним принудительный режим; None — авто
        if not getattr(self, "_icon_buttons", None):
            return
        base, hover, active, disabled = self._icon_colors()
        for btn, path, _, icon_size in self._icon_buttons:
            btn.setIcon(self._compose_stateful_icon(path, base, hover, active, disabled, icon_size))
    
    # ─────────────────────────── theme toggles & events ────────────────────────
    def set_dark_theme(self):
        # здесь может быть твоя логика палитры/стилей для всего окна
        self._forced_theme = "dark"
        self.apply_navbar_theme("dark")
    
    def set_light_theme(self):
        self._forced_theme = "light"
        self.apply_navbar_theme("light")
    
    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.StyleChange):
            # При любой смене палитры/стиля перерисуем наборы иконок
            if getattr(self, "_icon_buttons", None):
                self.apply_navbar_theme(None)
            else:
                self._pending_theme_apply = True





    
    def handle_mailto_url(self, mailto_url):
        """
        Обработка mailto: на высшем уровне.
        Режимы:
          - smart:   сначала QDesktopServices (системный клиент), иначе fallback -> gmail|outlookweb|custom
          - system:  только системный клиент ОС
          - gmail:   открывать Gmail compose во вкладке
          - outlookweb: Outlook (web) compose во вкладке
          - custom:  твой встроенный композер (self.mailto_compose_url)
        """
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        import urllib.parse as up
    
        # ----- настройки с дефолтами -----
        mode      = getattr(self, "mailto_mode", "smart")
        fallback  = getattr(self, "mailto_fallback", "gmail")
        compose_u = getattr(self, "mailto_compose_url", "http://127.0.0.1:5000/compose")
    
        # ----- утилиты -----
        def _b(s):
            # bytes из Qt QByteArray/str
            if hasattr(s, "data"):
                try:    return bytes(s.data())
                except: return bytes(s)
            if isinstance(s, bytes): return s
            return str(s).encode("utf-8", "ignore")
    
        def _dec(x):
            # безопасная percent-decoding
            return up.unquote(x or "")
    
        def _enc(x):
            # безопасная percent-encoding для URL-квери
            return up.quote(x or "", safe="")
    
        def _split_addrs(s):
            # разделители , или ; + чистим пробелы
            s = (s or "").replace(";", ",")
            parts = [p.strip() for p in s.split(",") if p.strip()]
            return parts
    
        def _idna(addr):
            # punycode для домена (user@домен)
            try:
                if "@" not in addr: 
                    return addr
                local, domain = addr.rsplit("@", 1)
                try:
                    domain_idna = domain.encode("idna").decode("ascii")
                except Exception:
                    domain_idna = domain
                return f"{local}@{domain_idna}"
            except Exception:
                return addr
    
        def _join_csv(lst):
            return ",".join([a for a in (lst or []) if a])
    
        # ----- парсинг mailto: -----
        url = mailto_url if isinstance(mailto_url, QUrl) else QUrl(str(mailto_url))
        raw = _b(url.toEncoded()).decode("utf-8", "ignore")  # гарантированно сырой вид
        if raw.lower().startswith("mailto:"):
            raw = raw[7:]
    
        to_part, _, qs = raw.partition("?")
        # адресаты из path
        to_addrs = _split_addrs(_dec(to_part))
    
        # параметры
        q = up.parse_qs(qs, keep_blank_values=True)
    
        # иногда попадается нестандартный ?to=
        if "to" in q:
            for val in q.get("to", []):
                to_addrs.extend(_split_addrs(_dec(val)))
    
        # нормализуем адреса (IDN и т.д.)
        to_addrs  = [_idna(a) for a in to_addrs]
        cc_addrs  = [_idna(a) for v in q.get("cc", [])  for a in _split_addrs(_dec(v))]
        bcc_addrs = [_idna(a) for v in q.get("bcc", []) for a in _split_addrs(_dec(v))]
    
        # subject/body (учтём су/subj варианты)
        subj = ""
        for k in ("subject", "su", "subj"):
            if k in q and q[k]:
                subj = _dec(q[k][0])
                break
        body = _dec(q.get("body", [""])[0] if q.get("body") else "")
    
        # ----- маршрутизация по режиму -----
        def open_system():
            # попробуем ровно тот mailto, что пришёл (сохранит то, что клиент поддерживает)
            ok = QDesktopServices.openUrl(mailto_url if isinstance(mailto_url, QUrl) else QUrl(str(mailto_url)))
            return bool(ok)
    
        def open_gmail():
            gmail = (
                "https://mail.google.com/mail/?view=cm&fs=1&tf=1"
                f"&to={_enc(_join_csv(to_addrs))}"
                f"&cc={_enc(_join_csv(cc_addrs))}"
                f"&bcc={_enc(_join_csv(bcc_addrs))}"
                f"&su={_enc(subj)}"
                f"&body={_enc(body)}"
                "&hl=ru"
            )
            self.add_new_tab(QUrl(gmail), "Gmail: жаңа хат")
    
        def open_outlookweb():
            # Подойдёт для live/outlook.office.com
            # Для enterprise можно подменить домен при желании
            outlook = (
                "https://outlook.live.com/mail/0/deeplink/compose"
                f"?to={_enc(_join_csv(to_addrs))}"
                f"&cc={_enc(_join_csv(cc_addrs))}"
                f"&bcc={_enc(_join_csv(bcc_addrs))}"
                f"&subject={_enc(subj)}"
                f"&body={_enc(body)}"
            )
            self.add_new_tab(QUrl(outlook), "Outlook: жаңа хат")
    
        def open_custom():
            # Твой встроенный композер (GET-параметры; если у тебя POST — меняй на своё)
            params = []
            if to_addrs:  params.append(f"to={_enc(_join_csv(to_addrs))}")
            if cc_addrs:  params.append(f"cc={_enc(_join_csv(cc_addrs))}")
            if bcc_addrs: params.append(f"bcc={_enc(_join_csv(bcc_addrs))}")
            if subj:      params.append(f"subject={_enc(subj)}")
            if body:      params.append(f"body={_enc(body)}")
            url = compose_u.rstrip("/") + ("/compose" if compose_u.rstrip("/").endswith(("compose","compose/")) is False else "")
            if "?" not in url:
                url += "?" + "&".join(params)
            else:
                url += "&" + "&".join(params)
            self.add_new_tab(QUrl(url), "Жаңа хат")
    
        try:
            if mode == "system":
                open_system()
                return
    
            if mode == "gmail":
                open_gmail()
                return
    
            if mode == "outlookweb":
                open_outlookweb()
                return
    
            if mode == "custom":
                open_custom()
                return
    
            # smart: пробуем системный; если не получилось — фолбэк
            if mode == "smart":
                if open_system():
                    return
                fb = (fallback or "gmail").lower()
                if fb == "gmail":
                    open_gmail(); return
                if fb == "outlookweb":
                    open_outlookweb(); return
                if fb == "custom":
                    open_custom(); return
                # если что-то экзотическое — gmail
                open_gmail(); return
    
            # Непонятный режим → системный, потом gmail
            if not open_system():
                open_gmail()
    
        except Exception as e:
            print("[mailto] error:", e)
            # последний шанс — системный клиент
            try: QDesktopServices.openUrl(mailto_url if isinstance(mailto_url, QUrl) else QUrl(str(mailto_url)))
            except: pass

    def _search_url(self, query_text: str) -> str:
        q = quote_plus(query_text or "")
        eng = (self.search_engine or "google").strip().lower()
        if eng == "google":
            return f"https://www.google.com/search?q={q}"
        if eng == "yandex":
            return f"https://yandex.ru/search/?text={q}"
        if eng == "duckduckgo":
            return f"https://duckduckgo.com/?q={q}"
        if eng == "bing":
            return f"https://www.bing.com/search?q={q}"
        if eng == "custom" and (self.search_custom or "").strip():
            # поддержка {query} и {q}
            tpl = (self.search_custom
                   .replace("{q}", "{query}")
                   .replace("{QUERY}", "{query}")
                   .replace("{Query}", "{query}"))
            try:
                return tpl.format(query=q)
            except Exception:
                pass
        # дефолт — Google
        return f"https://www.google.com/search?q={q}"





    def set_user_agent(self):
        user_agent = "SalemBrowser/4.5 (Qt5; PyQt5; SalemCorp)"
        self.web_view.page().profile().setHttpUserAgent(user_agent)
        

    def open_chatgpt_dock(self):
        """Открыть/закрыть боковую панель ChatGPT Messenger."""
        if self.chatgpt_dock is None:
            self.chatgpt_dock = QDockWidget("ChatGPT Messenger", self)
            self.chatgpt_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)

            chat_view = QWebEngineView()
            chat_view.setUrl(QUrl("https://chat.openai.com/"))  # или твой локальный сервер
            self.chatgpt_dock.setWidget(chat_view)

            self.addDockWidget(Qt.RightDockWidgetArea, self.chatgpt_dock)

        if self.chatgpt_dock.isVisible():
            self.chatgpt_dock.hide()
        else:
            self.chatgpt_dock.show()
            self.chatgpt_dock.raise_()



    def _shortcut(self, seq, handler):
        """Создаёт глобальный шорткат (работает при любом фокусе)."""
        if not hasattr(self, "_shortcuts"):
            self._shortcuts = []
        ks = seq if isinstance(seq, QKeySequence) else QKeySequence(seq)
        sc = QShortcut(ks, self)
        sc.setContext(Qt.ApplicationShortcut)
        # Если handler требует безаргументный вызов — ок, иначе оборачиваем
        sc.activated.connect(lambda: handler() if callable(handler) else None)
        self._shortcuts.append(sc)
        return sc

    def apply_global_theme(self, dark: bool):
        """Централизованная смена темы + экспонирование признака темы через app/window property."""
        palette = QPalette()
        if dark:
            palette.setColor(QPalette.Window, QColor("#23272e"))
            palette.setColor(QPalette.WindowText, QColor("#eaeaea"))
            palette.setColor(QPalette.Base, QColor("#181b22"))
            palette.setColor(QPalette.AlternateBase, QColor("#282a36"))
            palette.setColor(QPalette.Text, QColor("#f8f8f2"))
            palette.setColor(QPalette.Button, QColor("#282a36"))
            palette.setColor(QPalette.ButtonText, QColor("#42fff7"))
            palette.setColor(QPalette.Highlight, QColor("#068ce6"))
            palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        else:
            palette.setColor(QPalette.Window, QColor("#f8fafc"))
            palette.setColor(QPalette.WindowText, QColor("#23272e"))
            palette.setColor(QPalette.Base, QColor("#ffffff"))
            palette.setColor(QPalette.AlternateBase, QColor("#eaeaea"))
            palette.setColor(QPalette.Text, QColor("#23272e"))
            palette.setColor(QPalette.Button, QColor("#e0e7ef"))
            palette.setColor(QPalette.ButtonText, QColor("#068ce6"))
            palette.setColor(QPalette.Highlight, QColor("#42fff7"))
            palette.setColor(QPalette.HighlightedText, QColor("#181b22"))


        app = QApplication.instance()
        # Сделаем признак темы доступным всем виджетам
        self.setProperty("theme", "dark" if dark else "light")

        css = self.global_stylesheet(dark)
        QApplication.instance().setStyleSheet(css)

        # подключаем панель к ГЛОБАЛЬНОМУ QSS
        if hasattr(self, "bookmarks_bar"):
            self.bookmarks_bar.set_global_stylesheet(css)

        # ВАЖНО: после глобального листа — локальный лист сайдбара, чтобы он перекрыл нужные цвета иконок
        try:
            if hasattr(self, "sidebar") and self.sidebar is not None:
                self.sidebar.apply_theme_from_anchor()
        except Exception:
            pass


        app.setStyleSheet(self.global_stylesheet(dark))
    def global_stylesheet(self, dark: bool) -> str:
        if dark:
            return """
            /* БАЗА */
            QWidget {
                background-color: #23272e;
                color: #eaeaea;
                font-size: 12px;
            }
            QMainWindow, QFrame, QTabWidget, QTabBar, QListWidget, QToolBar, QStatusBar {
                background-color: #23272e;
                color: #eaeaea;
            }
    
            /* ИНПУТЫ / РЕДАКТОРЫ / СПИНЫ / КОМБО */
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #1f1f2b;
                color: #f2f2f2;
                border: 2px solid #3e4a66;   /* фиксированная толщина */
                border-radius: 6px;
                padding: 8px 12px;
                selection-background-color: #42fff7;
                selection-color: #1f1f2b;
            }
            QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
            QSpinBox:hover, QDoubleSpinBox:hover {
                border-color: #5bd7ff;
                background-color: #252839;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
            QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #ff79c6;
                background-color: #2c2e3f;
            }
    
            /* ВЫПАДАЮЩИЙ СПИСОК КОМБОБОКСА */
            QComboBox QAbstractItemView {
                background: #1f1f2b;
                color: #eaeaea;
                border: 1px solid #3e4a66;
                selection-background-color: #35384a;
                selection-color: #42fff7;
            }
    
            /* СПИСКИ/ТАБЛИЦЫ (общая логика выбора) */
            QAbstractItemView {
                background: #23272e;
                color: #eaeaea;
                border: 1px solid #44475a;
                selection-background-color: #35384a;
                selection-color: #42fff7;
            }
    
            /* ТУЛБАР ЗАКЛАДОК (если objectName == bookmarks_bar) */
            QToolBar#bookmarks_bar { background: transparent; spacing: 6px; }
            QToolBar#bookmarks_bar QToolButton {
                min-width: 10px; padding: 2px 6px; border-radius: 6px;
            }
            QToolBar#bookmarks_bar QToolButton:hover { background: #2c3140; }
            QToolBar#bookmarks_bar QToolButton:pressed { background: #068ce6; color: #fff; }
    
            /* КНОПКИ ОБЩИЕ (НЕ ДЕЛАЕМ ВСЁ КВАДРАТНЫМ) */
            QPushButton {
                background-color: #282a36;
                color: #42fff7;
                border: 1px solid #44475a;
                border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #35384a; }
            QPushButton:pressed { background-color: #068ce6; color: #fff; }
    
            /* ИКОН-КНОПКИ (ТОЛЬКО ТЕМ, КОМУ НУЖНО 32×32) */
            QPushButton#iconBtn, QToolButton#iconBtn {
                min-width: 32px; max-width: 32px;
                min-height: 32px; max-height: 32px;
                padding: 0; border-radius: 6px;
            }
    
            /* ТУЛКНОПКИ ПО УМОЛЧАНИЮ */
            QToolButton {
                background: transparent;
                border: none;
                padding: 0;
                border-radius: 6px;
            }
            QToolButton:hover { background-color: #35384a; }
            QToolButton:pressed { background-color: #068ce6; color: #fff; }
    
            /* ТАБЫ */
            QTabWidget::pane {
                border: 1px solid #44475a;
                border-radius: 8px;
                top: 6px;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #eaeaea;
                border: 1px solid #44475a;
                border-radius: 8px;
                padding: 7px 18px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background: #23272e;
                color: #42fff7;
                border-color: #5bd7ff;
            }
    
            /* СКРОЛЛБАРЫ */
            QScrollBar:vertical {
                background: #23272e; width: 10px; border: none;
            }
            QScrollBar:horizontal {
                background: #23272e; height: 10px; border: none;
            }
            QScrollBar::handle:vertical { background: #44475a; border-radius: 5px; }
            QScrollBar::handle:horizontal { background: #44475a; border-radius: 5px; }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #068ce6; }
    
            /* МЕНЮ */
            QMenu { background-color: #23272e; color: #eaeaea; border: 1px solid #44475a; }
            QMenu::item:selected { background: #35384a; color: #42fff7; }
    
            /* СТАТУСБАР */
            QStatusBar { color: #eaeaea; }
            """
        else:
            return """
            QWidget { background-color: #f8fafc; color: #23272e; font-size: 12px; }
            QMainWindow, QFrame, QTabWidget, QTabBar, QListWidget, QToolBar, QStatusBar {
                background-color: #f8fafc; color: #23272e;
            }
    
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #ffffff;
                color: #23272e;
                border: 2px solid #c7d2fe;
                border-radius: 6px;
                padding: 8px 12px;
                selection-background-color: #42fff7;
                selection-color: #0f172a;
            }
            QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QComboBox:hover,
            QSpinBox:hover, QDoubleSpinBox:hover { border-color: #68a8ff; }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
            QSpinBox:focus, QDoubleSpinBox:focus { border-color: #068ce6; }
    
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #23272e;
                border: 1px solid #c7d2fe;
                selection-background-color: #e0e7ef;
                selection-color: #068ce6;
            }
    
            QAbstractItemView {
                background: #f8fafc;
                color: #23272e;
                border: 1px solid #c7d2fe;
                selection-background-color: #e0e7ef;
                selection-color: #068ce6;
            }
    
            QToolBar#bookmarks_bar { background: transparent; spacing: 6px; }
            QToolBar#bookmarks_bar QToolButton {
                min-width: 10px; padding: 2px 6px; border-radius: 6px;
            }
            QToolBar#bookmarks_bar QToolButton:hover { background: #dbeafe; }
            QToolBar#bookmarks_bar QToolButton:pressed { background: #42fff7; color: #fff; }
    
            QPushButton {
                background-color: #e0e7ef; color: #068ce6;
                border: 1px solid #c7d2fe; border-radius: 6px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #dbeafe; }
            QPushButton:pressed { background-color: #42fff7; color: #fff; }
    
            QPushButton#iconBtn, QToolButton#iconBtn {
                min-width: 32px; max-width: 32px;
                min-height: 32px; max-height: 32px;
                padding: 0; border-radius: 6px;
            }
    
            QToolButton {
                background: transparent; border: none; padding: 0; border-radius: 6px;
            }
            QToolButton:hover { background-color: #e9eef8; }
            QToolButton:pressed { background-color: #42fff7; color: #fff; }
    
            QTabWidget::pane {
                border: 1px solid #c7d2fe;
                border-radius: 8px;
                top: 6px;
            }
            QTabBar::tab {
                background-color: #eef1f7; color: #23272e;
                border: 1px solid #c7d2fe; border-radius: 8px;
                padding: 7px 18px; margin-right: 4px;
            }
            QTabBar::tab:selected { background: #ffffff; color: #068ce6; border-color: #68a8ff; }
    
            QScrollBar:vertical { background: #eef1f7; width: 10px; border: none; }
            QScrollBar:horizontal { background: #eef1f7; height: 10px; border: none; }
            QScrollBar::handle:vertical { background: #c7d2fe; border-radius: 5px; }
            QScrollBar::handle:horizontal { background: #c7d2fe; border-radius: 5px; }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover { background: #42fff7; }
    
            QMenu { background-color: #f8fafc; color: #23272e; border: 1px solid #c7d2fe; }
            QMenu::item:selected { background: #e0e7ef; color: #068ce6; }
    
            QStatusBar { color: #23272e; }
            """

        
    # Waiting for refactoring....
    def _open_server_error_page(self, webview, code: str = "503", msg: str = ""):
        base = getattr(self, "error_base_url", "http://127.0.0.1:5000")
        cur  = webview.url().toString()

        # защитимся от рекурсии: если уже на нашей странице ошибок — не перенаправляем
        if cur.startswith(base + "/error") or cur.startswith(base + "/errors"):
            return

        url = QUrl(f"{base}/error/{code}")    # у тебя уже есть маршруты/декораторы → используем /error/<code>
        q = QUrlQuery()
        if cur: q.addQueryItem("src", cur)
        if msg: q.addQueryItem("msg", msg[:300])
        url.setQuery(q)
        webview.setUrl(url)

    def install_error_reactions(self, webview):
        # 1) Если страница НЕ загрузилась (сетевой/фатальный фейл) — переводим вкладку на /error/503
        webview.loadFinished.connect(
            lambda ok, v=webview: (None if ok else self._open_server_error_page(v, "503", "network-fail"))
        )

        # 2) Если сервер сам отдал свою ошибку (твои шаблоны уже включают мета-маркер) — ничего делать не надо:
        #    страница ошибки уже рендерится во вкладке. Оставляем только авто-склейку заголовка вкладки:
        def _normalize_title():
            t = v.page().title()
            if not t: return
            # опционально можно подсветить код из <meta name="x-salem-error">
            v.page().runJavaScript(
                "(()=>{var m=document.querySelector('meta[name=\"x-salem-error\"]');return m?m.content:'';})()",
                lambda code: self.tabs.setTabText(self.tabs.indexOf(v), f"{t}" if not code else f"{t} [{code}]")
            )

        v = webview
        v.titleChanged.connect(lambda _=None: _normalize_title())

        
    def init_tab_ui(self):
        # не пересоздаём, если уже стоит AnimatedTabBar
        bar = self.tabs.tabBar()
        if not isinstance(bar, AnimatedTabBar):
            bar = AnimatedTabBar(self.tabs)
            self.tabs.setTabBar(bar)

        # IMPORTANT: путь через self._asset, чтобы работало и в PyInstaller
        bar.set_loading_gif(self._asset("img/icons/loader.gif"), size=16)

        self.tabs.setMovable(True)
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_current_tab)

        # минимальная косметика
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: 0; margin: 0; padding: 0; }
            QTabWidget { margin: 0; padding: 0; }
        """)

        # плавная подсветка индикатора
        self.tabs.currentChanged.connect(bar.animate_to)
        try:
            bar.tabMoved.connect(lambda _f, t: bar.animate_to(t))
        except Exception:
            pass
        QTimer.singleShot(0, lambda: bar.animate_to(self.tabs.currentIndex()))





    def _progress_icon(self, percent: int, size: int = 16) -> QIcon:
        p = max(0, min(100, int(percent)))
        pm = QPixmap(size, size); pm.fill(Qt.transparent)
        painter = QPainter(pm); painter.setRenderHint(QPainter.Antialiasing, True)
        pen_bg = QPen(QColor("#475569")); pen_bg.setWidth(2); painter.setPen(pen_bg)
        painter.drawEllipse(2, 2, size-4, size-4)
        pen_fg = QPen(QColor("#2dd4bf")); pen_fg.setWidth(2); painter.setPen(pen_fg)
        span = int(360 * 16 * (p/100.0))
        painter.drawArc(2, 2, size-4, size-4, 90*16, -span)
        painter.end()
        return QIcon(pm)

    def _on_load_started(self, view):
        i = self.tabs.indexOf(view)
        if i >= 0: self.tabs.setTabIcon(i, self._progress_icon(1))

    def _on_load_progress(self, view, progress: int):
        i = self.tabs.indexOf(view)
        if i >= 0: self.tabs.setTabIcon(i, self._progress_icon(progress))

    def _on_load_finished(self, view, ok: bool):
        i = self.tabs.indexOf(view)
        if i >= 0:
            icon = view.icon()
            self.tabs.setTabIcon(i, icon if not icon.isNull() else self._progress_icon(100))



        
    def toggle_max_restore(self):
        self.titlebar.toggle_max_restore()



    def setup_hotkeys(self):
        # PiP-режим — Alt+Shift+P
        QShortcut(QKeySequence("Alt+Shift+P"), self, self.menu_pip_native)
        # Новая вкладка — Ctrl+T
        QShortcut(QKeySequence("Ctrl+N"), self, self.add_new_tab)
        # Закрыть вкладку — Ctrl+W
        QShortcut(QKeySequence("Ctrl+Q"), self, lambda: self.close_current_tab(self.tabs.currentIndex()))
        # Следующая вкладка — Ctrl+Tab
        QShortcut(QKeySequence("Ctrl+Tab"), self, self.next_tab)
        # Предыдущая вкладка — Ctrl+Shift+Tab
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self.prev_tab)
        # Обновить страницу — F5
        QShortcut(QKeySequence("F5"), self, self.refresh_page)
        # Домой — Alt+Home
        QShortcut(QKeySequence("Alt+H"), self, self.navigate_home)
        # Назад — Alt+Left
        QShortcut(QKeySequence("Alt+Left"), self, self.navigate_back)
        # Вперёд — Alt+Right
        QShortcut(QKeySequence("Alt+Right"), self, self.navigate_forward)
        # Фокус на адресную строку — Ctrl+L
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.url_bar.setFocus())
        # Открыть меню — Alt+M
        QShortcut(QKeySequence("Alt+M"), self, self.open_menu)
        # PiP-режим — Ctrl+P
        QShortcut(QKeySequence("Ctrl+P"), self, self.menu_pip_mode)
        # Загрузки — Ctrl+J
        QShortcut(QKeySequence("Ctrl+J"), self, self.open_downloads_tab)
        # История — Ctrl+H
        QShortcut(QKeySequence("Ctrl+H"), self, self.open_history_tab)
        # DevTools — F12
        QShortcut(QKeySequence("F12"), self, self.toggle_devtools)
        # Расширения — Ctrl+E
        QShortcut(QKeySequence("F11"), self, self.toggle_max_restore)




    def inject_pip_button(self, webview=None):
        """Рисуем кнопку ⧉ поверх QWebEngineView. Никакого JS."""
        if webview is None:
            webview = self.tabs.currentWidget()
        if not webview:
            return
        if hasattr(webview, "_pip_btn") and webview._pip_btn:
            return

        btn = QPushButton("⧉", parent=webview)
        # ХОРОШО — стиль только на нашу кнопку
        btn.setObjectName("pipOverlayBtn")
        btn.setStyleSheet("""
        #pipOverlayBtn {
            background: #2b3445;
            border: none;
            color: #fff;
            border-radius: 6px;
            padding: 6px 10px;
        }
        #pipOverlayBtn:hover { background: #3b4559; }
        """)


        def _reposition():
            x = max(10, webview.width() - btn.width() - 10)
            y = 10
            btn.move(x, y)

        _reposition()

        class _PipOverlayFilter(QObject):
            def __init__(self, rep, parent=None):
                super().__init__(parent)
                self._rep = rep
            def eventFilter(self, obj, ev):
                if ev.type() in (QEvent.Resize, QEvent.Show, QEvent.Move):
                    self._rep()
                return False

        filt = _PipOverlayFilter(_reposition, webview)
        webview.installEventFilter(filt)

        # лёгкий стиль (опционально)
        try:
            webview.setStyleSheet(webview.styleSheet() + """
            #pipOverlayBtn { background:#2b3445; border:none; color:#fff; border-radius:6px; }
            #pipOverlayBtn:hover { background:#3b4559; }
            """)
        except Exception:
            pass

        webview._pip_btn = btn
        webview._pip_filter = filt



    def setup_pip_handler(self, webview=None):
        if webview is None:
            webview = self.tabs.currentWidget()
        if not webview:
            return

        # Не плодим шорткаты
        if hasattr(webview, "_pip_shortcut"):
            return

        sc = QShortcut(QKeySequence("Alt+Shift+P"), webview)
        sc.setContext(3)  # Qt.ApplicationShortcut или WidgetWithChildren — можно оставить по умолчанию
        sc.activated.connect(self.menu_pip_mode)

        webview._pip_shortcut = sc

    def menu_pip_mode(self):
        """Toggle PiP: выносим текущий QWebEngineView в стеклянное PiP-окно и обратно."""
        try:
            # У тебя уже есть импорт вверху: from modules.pip_mode import PipWindow
            # Если где-то запуск отдельно — оставлю safety-импорт:
            from modules.pip_mode import PipWindow  # noqa
        except Exception as e:
            print("[PiP] import failed:", e)
            return

        # Если PiP уже открыт — закрываем (это вернёт вкладку)
        if getattr(self, "pip_window", None) and self.pip_window.isVisible():
            self.pip_window.close()
            return

        # Извлекаем текущий WebView из вкладки
        triplet = self._detach_view_to_pip()
        if not triplet:
            return
        idx, view, placeholder = triplet

        # Создаём стеклянное окно PiP и «усыновляем» туда view
        self.pip_window = PipWindow(self)
        self.pip_window.adopt_view(view)

        # Когда PiP закрывается — возвращаем view назад в ту же вкладку
        def _on_pip_closed():
            try:
                v = self.pip_window.release_view()
            except Exception:
                v = view  # на всякий
            try:
                self._attach_view_back(idx, v, placeholder)
            finally:
                self.pip_window = None

        self.pip_window.closed.connect(_on_pip_closed)

        # Позиционируем PiP справа-сверху главного окна
        geo = self.geometry()
        pw, ph = 560, 320
        x = geo.right() - pw - 24
        y = geo.top() + 80
        self.pip_window.resize(pw, ph)
        self.pip_window.move(x, y)
        self.pip_window.show()



    def _restore_from_pip(self):
        st = getattr(self, "_pip_state", None)
        if not st:
            if getattr(self, "pip_window", None):
                self.pip_window.close()
                self.pip_window = None
            return

        v, idx, label, icon = st["view"], max(0, min(st["index"], self.tabs.count())), st["label"], st["icon"]
        if getattr(self, "pip_window", None):
            try: self.pip_window.closed.disconnect(self._restore_from_pip)
            except Exception: pass
            self.pip_window.release_view()
            self.pip_window.close()
            self.pip_window = None

        if v:
            i = self.tabs.insertTab(idx, v, label)
            if icon: self.tabs.setTabIcon(i, icon)
            self.tabs.setCurrentIndex(i)

        self._pip_state = None


    # ───────── PiP plumbing: извлечь/вернуть QWebEngineView ─────────
    def _current_webview(self):
        try:
            w = self.tabs.currentWidget()
            if isinstance(w, QWebEngineView):
                return w
                if w:
                    v = w.findChild(QWebEngineView)
                    if v:
                        return v
        except Exception:
            pass
        return None

    def _make_pip_placeholder(self, title: str):
        from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
        ph = QWidget()
        lay = QVBoxLayout(ph); lay.setContentsMargins(24, 28, 24, 24); lay.setSpacing(12)
        lbl = QLabel(f"Видео вынесено в Picture-in-Picture<br><small>{title}</small>")
        lbl.setStyleSheet("color:#a9b4d6; font-size:15px;")
        btn = QPushButton("Вернуть из PiP")
        btn.setStyleSheet("padding:8px 12px;")
        btn.clicked.connect(lambda: getattr(self, "menu_pip_mode", lambda: None)())
        lay.addWidget(lbl, 0); lay.addWidget(btn, 0); lay.addStretch(1)
        return ph

    def _detach_view_to_pip(self):
        """Заменяет текущую вкладку заглушкой и возвращает (idx, view, placeholder)."""
        from PyQt5.QtWebEngineWidgets import QWebEngineView
        view = self._current_view()
        if not view:
            return None
        idx = self.tabs.currentIndex()
        title = self.tabs.tabText(idx) or "PiP"
        placeholder = self._make_pip_placeholder(title)

        # Вкладываем заглушку на место живого view (сохраняя позицию вкладки)
        self.tabs.removeTab(idx)
        self.tabs.insertTab(idx, placeholder, title)
        self.tabs.setCurrentIndex(idx)

        # Полностью отсоединяем view, чтобы перепривязать его к PipWindow
        view.setParent(None)
        view.hide()
        return (idx, view, placeholder)

    def _attach_view_back(self, idx: int, view, placeholder):
        """Возвращает view в ту же вкладку вместо заглушки."""
        if not (0 <= idx < self.tabs.count()):
            idx = self.tabs.currentIndex()

        title = self.tabs.tabText(idx) or "Tab"
        try:
            self.tabs.removeTab(idx)   # убрать заглушку
        except Exception:
            pass

        self.tabs.insertTab(idx, view, title)
        self.tabs.setCurrentIndex(idx)
        view.show()
        view.setFocus()

    def _js_get_video_and_hide(self, view):
            js = r"""
        (function(){
          const v = document.querySelector("video");
          if(!v) return JSON.stringify({ok:false, reason:"NO_VIDEO"});
          const src = v.currentSrc || v.src || "";
          try { v.pause(); v.style.visibility="hidden"; v.style.display="none"; } catch(e){}
          return JSON.stringify({ok:true, src:src, href: location.href});
        })();"""
            def _done(res):
                pass
            view.page().runJavaScript(js, _done)
            return js  # просто чтобы было

    def _js_restore_video(self, view):
            js = r"""
        (function(){
          const v = document.querySelector("video");
          if(!v) return;
          v.style.removeProperty("visibility");
          v.style.removeProperty("display");
          try { v.play(); } catch(e){}
        })();"""
            view.page().runJavaScript(js)

    def menu_pip_native(self):
            """PiP на QMediaPlayer: выдёргиваем прямой URL (или через yt-dlp) и играем нативно."""
            view = getattr(self.tabs, "currentWidget", lambda: None)()
            try:
                from PyQt5.QtWebEngineWidgets import QWebEngineView
            except:
                QWebEngineView = None
            if not (QWebEngineView and isinstance(view, QWebEngineView)):
                return

            # 1) получить src/href из страницы и скрыть <video>
            js = r"""
        (function(){
          const v = document.querySelector("video");
          if(!v) return JSON.stringify({ok:false, reason:"NO_VIDEO"});
          const src = v.currentSrc || v.src || "";
          try { v.pause(); v.style.visibility="hidden"; v.style.display="none"; } catch(e){}
          return JSON.stringify({ok:true, src:src, href: location.href});
        })();"""
            def _after_js(payload):
                import json
                try:
                    data = json.loads(payload) if isinstance(payload, str) else {}
                except Exception:
                    data = {}
                ok = bool(data.get("ok"))
                src = data.get("src") or ""
                href = data.get("href") or ""
                page_url = href or view.url().toString()

                # 2) запускаем PiP окно
                self.pip_native = PiPMediaWindow(self)
                # позиция
                geo = self.geometry(); pw, ph = 560, 320
                self.pip_native.resize(pw, ph)
                self.pip_native.move(geo.right()-pw-24, geo.top()+80)
                self.pip_native.show()

                def _cleanup():
                    # вернуть видео на страницу
                    try: self._js_restore_video(view)
                    except: pass
                    self.pip_native = None

                self.pip_native.closed.connect(_cleanup)

                # 3) если src уже прямой — играем; иначе добываем через yt-dlp по page_url
                def _play_direct(url):
                    if url:
                        self.pip_native.play_url(url)
                        return True
                    return False

                if ok and src and not src.startswith("blob:"):
                    if _play_direct(src):
                        return

                # 4) blob/пусто → yt-dlp
                try:
                    from modules.pip_native import _FetchWorker
                    from PyQt5.QtCore import QThread
                    self._pip_dl_thread = QThread(self)
                    self._pip_worker = _FetchWorker(page_url)
                    self._pip_worker.moveToThread(self._pip_dl_thread)
                    self._pip_dl_thread.started.connect(self._pip_worker.run)
                    def _on_ready(url, err):
                        try:
                            if url:
                                self.pip_native.play_url(url)
                            else:
                                # fallback: не удалось — просто вернём <video> на страницу
                                try: self._js_restore_video(view)
                                except: pass
                        finally:
                            self._pip_dl_thread.quit()
                            self._pip_dl_thread.wait()
                    self._pip_worker.finished.connect(_on_ready)
                    self._pip_dl_thread.start()
                except Exception as e:
                    # нет yt-dlp — откат
                    try: self._js_restore_video(view)
                    except: pass

            view.page().runJavaScript(js, _after_js)





    def closeEvent(self, event):
        # закрыть все вкладки, чтобы страницы освободились
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        event.accept()

    def _schedule_repolish(self, *widgets):
        """Оптимизированная «отложенная» полировка стилей, чтобы не лагало"""
        if getattr(self, "_repolish_scheduled", False):
            return
        self._repolish_scheduled = True

        def _do():
            self._repolish_scheduled = False
            for w in widgets:
                if w:
                    try:
                        w.style().unpolish(w)
                        w.style().polish(w)
                    except Exception:
                        pass
        QTimer.singleShot(0, _do)

    def current_tab_changed(self, i: int):
        """Смена активной вкладки: адресная строка, DevTools, инъекции, медиа-контроль."""
        try:
            count = self.tabs.count()
            if i < 0 or i >= count:
                return

            view = self.tabs.widget(i)
            from PyQt5.QtWebEngineWidgets import QWebEngineView

            # ── СЛУЖЕБНЫЕ ВКЛАДКИ (не WebView) → просто показать псевдо-URL и выйти
            if not isinstance(view, QWebEngineView):
                try:
                    if view is getattr(self, "history_panel", None):
                        self.url_bar.setText("hist://history"); self.url_bar.setCursorPosition(0)
                    elif view is getattr(self, "downloads_panel", None):
                        self.url_bar.setText("dl://downloads"); self.url_bar.setCursorPosition(0)
                    else:
                        # если появятся другие сервисные панели — можно дописать сюда
                        self.url_bar.setText(""); self.url_bar.setCursorPosition(0)
                except Exception:
                    pass
                return

            # ── 1) Адресная строка
            try:
                self.update_urlbar(view.url(), view)
            except Exception as e:
                print("[tabs] update_urlbar failed:", e)

            # ── 2) Проводка инъекций/обработчиков — один раз на вкладку
            if not getattr(view, "_sx_wired", False):

                def _on_load_finished(ok, v=view):
                    if ok:
                        try:
                            self.extension_loader.inject_into(v)
                        except Exception as e2:
                            print("[tabs] inject_into failed:", e2)

                view._sx_on_load_finished = _on_load_finished
                try:
                    view.loadFinished.connect(view._sx_on_load_finished)
                except Exception:
                    pass

                # PiP-кнопка и обработчики
                try:
                    self.inject_pip_button(view)
                    self.setup_pip_handler(view)
                except Exception as e:
                    print("[tabs] PIP wiring failed:", e)

                view._sx_wired = True

            # ── 3) DevTools к активной вкладке
            try:
                if self.devtools and not self.devtools.isVisible():
                    self.devtools.detach()  # не держим inspectedPage в фоне
            except Exception:
                pass

            # ── 4) Медиа-контроль: активная — unmute; фоновые web-табы — mute + pause()
            for n in range(count):
                w = self.tabs.widget(n)
                if isinstance(w, QWebEngineView):
                    page = w.page()
                    if n == i:
                        try:
                            page.setAudioMuted(False)
                        except Exception:
                            pass
                    else:
                        try:
                            page.setAudioMuted(True)
                        except Exception:
                            pass
                        try:
                            page.runJavaScript("""
                                (function(){
                                    try{
                                        document.querySelectorAll('video,audio')
                                               .forEach(function(m){ try{ m.pause(); }catch(e){} });
                                    }catch(e){}
                                })();
                            """)
                        except Exception:
                            pass

        except Exception as e:
            print("[tabs] current_tab_changed fatal:", e)


    def on_tab_close_requested(self, index: int):
        self.close_current_tab(index)



    def _pause_media_js(self, view: QWebEngineView):
        """Поставить на паузу любые <video>/<audio> на странице."""
        try:
            view.page().runJavaScript("""
                (function(){
                    try{
                        document.querySelectorAll('video,audio').forEach(function(m){
                            try{ m.pause(); }catch(e){}
                            // в фоновых вкладках часто хватает паузы;
                            // если хочешь агрессивнее — раскомментируй сброс источника:
                            // try{ m.src=''; m.removeAttribute('src'); m.load(); }catch(e){}
                        });
                    }catch(e){}
                })();
            """)
        except Exception:
            pass

    def _stop_media_in(self, view: QWebEngineView):
        """Мгновенно глушит звук и останавливает активность страницы."""
        if not isinstance(view, QWebEngineView):
            return
        page = view.page()
        try: page.setAudioMuted(True)
        except Exception: pass
        try: page.triggerAction(QWebEnginePage.Stop)   # стоп загрузок/действий
        except Exception: pass
        self._pause_media_js(view)
        try: page.setDevToolsPage(None)                # на всякий случай отвязать devtools
        except Exception: pass

    def _dispose_view(self, view: QWebEngineView):
        """Корректно освобождает ресурсы WebEnginePage/WebView."""
        if not isinstance(view, QWebEngineView):
            return
        try:
            page = view.page()
            view.setParent(None)
            if page:
                page.deleteLater()
            view.deleteLater()
        except Exception:
            pass

    def on_tab_close_requested(self, index: int):
        try:
            view = self.tabs.widget(index)
            # если у тебя есть PiP – верни его назад, чтобы не завис
            try:
                if hasattr(self, "_restore_from_pip"):
                    self._restore_from_pip()
            except Exception:
                pass

            # 1) Глушим и останавливаем
            self._stop_media_in(view)

            # 2) Убираем вкладку из TabWidget (обрывает большинство сигналов)
            self.tabs.removeTab(index)

            # 3) Финально утилизируем страницу/вью
            self._dispose_view(view)
        except Exception as e:
            print("[tabs] on_tab_close_requested failed:", e)



                    
    def _safe_set_tab_text(self, view, text):
        """Безопасно обновляем заголовок вкладки, даже если tabs уже удалён."""
        try:
            if self.tabs and not sip.isdeleted(self.tabs):
                idx = self.tabs.indexOf(view)
                if idx >= 0:
                    self.tabs.setTabText(idx, text)
        except Exception:
            pass

    def _is_internal_url(self, url) -> bool:
        """True для наших служебных схем и псевдо-URL."""
        s = (url.toString() if hasattr(url, "toString") else str(url)).strip().lower()
        return (
            s.startswith(( "configure:/", "app:/", "downloads:/", "downloads://", "mods:/", "mods://"))
            or s == "about:blank"
            or s.startswith("data:")
        )

    def update_urlbar(self, qurl, webview=None):
        """Обновляет адресную строку (и историю) для активной вкладки."""
        if webview is not self.tabs.currentWidget():
            return

        # Если это домашняя страница — скрываем адрес, показываем плейсхолдер
        if self._is_home_url(qurl):
            try:
                self.url_bar.blockSignals(True)
                self.url_bar.clear()
                # аккуратный плейсхолдер (любой свой текст)
                self.url_bar.setPlaceholderText("Новая вкладка — введите запрос или адрес")
                self.url_bar.setCursorPosition(0)
            finally:
                self.url_bar.blockSignals(False)
            # Домашнюю в историю не пишем
            return

        # Обычные адреса — показываем как есть
        text = self._url_str(qurl)
        self.url_bar.setText(text)
        self.url_bar.setCursorPosition(0)

        # В историю — только «нормальные» внешние URL (не служебные/домашние)
        if not webview or self._is_internal_url(qurl) or self._is_home_url(qurl):
            return
        if getattr(self, "history_panel", None):
            try:
                self.history_panel.add_entry(text, webview.title())
            except Exception as e:
                print("[history] add_entry failed:", e)


    def on_tab_changed(self, index):
        """Переключение вкладок — подключаем обработчик загрузок на текущую страницу."""
        current = self.tabs.widget(index)
        if isinstance(current, QWebEngineView):
            url = current.url().toString()
            title = current.title()
            self.history_panel.add_entry(url, title)



    def set_user_agent(self):
        """Устанавливает максимальный User-Agent и web-настройки для всех вкладок."""
        custom_user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 "
            "Safari/537.36 "
            "OPR/108.0.0.0"
        )
        current_webview = self.tabs.currentWidget()
        if isinstance(current_webview, QWebEngineView):
            profile = current_webview.page().profile()
            profile.setHttpUserAgent(custom_user_agent)
            settings = current_webview.settings()
            # Основные
            settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
            settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
            settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)
            settings.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
            settings.setAttribute(QWebEngineSettings.WebGLEnabled, True)
            settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
            settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            # Новое API (где доступно)
            if hasattr(QWebEngineSettings, "XSSAuditingEnabled"):
                settings.setAttribute(QWebEngineSettings.XSSAuditingEnabled, False)
            if hasattr(QWebEngineSettings, "ScreenCaptureEnabled"):
                settings.setAttribute(QWebEngineSettings.ScreenCaptureEnabled, True)
            if hasattr(QWebEngineSettings, "PdfViewerEnabled"):
                settings.setAttribute(QWebEngineSettings.PdfViewerEnabled, True)
            if hasattr(QWebEngineSettings, "WebRTCPublicInterfacesOnly"):
                settings.setAttribute(QWebEngineSettings.WebRTCPublicInterfacesOnly, False)
            if hasattr(QWebEngineSettings, "Accelerated2dCanvasEnabled"):
                settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, True)
            if hasattr(QWebEngineSettings, "ErrorPageEnabled"):
                settings.setAttribute(QWebEngineSettings.ErrorPageEnabled, True)

            # Печать для контроля
            print("✅ User-Agent установлен:", custom_user_agent)
            print("✅ JS, WebGL, Clipboard, FullScreen, LocalStorage и всё крутое включено.")

    
    def _parse_internal_url(self, s: str):
        """Возвращает (scheme, target, params) для псевдо-URL вида configure://..."""
        url = QUrl(s)
        scheme = (url.scheme() or "").lower()
        # поддерживаем и configure://target и configure:///target
        host = (url.host() or "").strip("/").lower()
        path = (url.path() or "").strip("/").lower()
        target = host or path  # итоговый «маршрут»
        q = QUrlQuery(url)
        params = {}
        try:
            for k, v in q.queryItems():
                params[k] = v
        except Exception:
            pass
        return scheme, target, params



    def add_new_tab(self, qurl=None, label="Жаңа бет"):
        """Создаёт новую вкладку: webview или встроенную страницу (downloads, mods, extensions, history).
        Полностью исправлено: нет несуществующих переменных, нет недостижимого кода, единая инициализация tabData.
        """
        # ───────── локальные импорты, чтобы не плодить зависимости ─────────
        from PyQt5.QtCore import QUrl
        from PyQt5.QtWebEngineWidgets import (
            QWebEngineView, QWebEngineSettings, QWebEnginePage
        )
    
        try:
            from modules.extensions_ui import ExtensionManager
        except Exception:
            ExtensionManager = None
        try:
            from modules.history_ui import HistoryPanel
        except Exception:
            HistoryPanel = None
        try:
            from modules.mods_ui import ModManager
        except Exception:
            ModManager = None
    
        # ───────── вспомогательная страница с поддержкой createWindow ─────────
        class _SafePage(QWebEnginePage):
            def __init__(pg_self, parent=None):
                super().__init__(self.profile, parent)
    
        # ───────── универсальная «провязка» сигналов и DevTools ─────────
        def _wire_view(view: QWebEngineView):
            # базовые сигналы загрузки
            view.loadStarted.connect(lambda sv=view: self._on_load_started(sv))
            view.loadProgress.connect(lambda p, sv=view: self._on_load_progress(sv, p))
            view.loadFinished.connect(lambda ok, sv=view: self._on_load_finished(sv, ok))
    
            # регистрация внутренних обработчиков (расширения/моды/хоткеи и т.п.)
            try:
                self._register_webview(view)
            except Exception:
                pass
            
            # DevTools (если есть)
            try:
                self.devtools.attach(view)
            except Exception:
                pass
            
            # Настройки движка
            s = view.settings()
            s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
            s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
            s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, True)      # важно для window.open
            s.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)
            s.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
            s.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
    
            # User-Agent (профиль)
            try:
                view.page().profile().setHttpUserAgent(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            except Exception:
                pass
            
            # Оптимизатор (если есть)
            try:
                if hasattr(self, "optimizer"):
                    self.optimizer.register_view(view)
            except Exception:
                pass
            
        # ───────── привязки, зависящие от индекса вкладки ─────────
        def _post_add(view: QWebEngineView, idx: int):
            bar = self.tabs.tabBar()
            # спиннер загрузки
            if hasattr(bar, "set_tab_loading"):
                view.loadStarted.connect(lambda sv=view, i=idx, b=bar: b.set_tab_loading(i, True))
                view.loadFinished.connect(lambda ok, sv=view, i=idx, b=bar: b.set_tab_loading(i, False))
            # mute-индикатор (если поддерживается)
            if hasattr(bar, "set_tab_muted"):
                try:
                    bar.set_tab_muted(idx, view.page().isAudioMuted())
                except Exception:
                    pass
            # синхронизация заголовка/иконки/адресной строки
            view.iconChanged.connect(lambda _ic, sv=view, i=idx: self.tabs.setTabIcon(i, sv.icon()))
            view.titleChanged.connect(lambda t, i=idx: self.tabs.setTabText(i, t or "…"))
            view.loadFinished.connect(lambda _ok, sv=view: self.update_urlbar(sv.url(), sv))
            view.urlChanged.connect(lambda url, sv=view: self.update_urlbar(url, sv))
    
        # ───────── фабрика WebView с нашей страницей ─────────
        def _new_view() -> QWebEngineView:
            v = QWebEngineView(self)
            p = _SafePage(parent=v)
            v.setPage(p)
            _wire_view(v)
            return v
    
        # ───────── служебные маршруты ─────────
        if qurl is None:
            qurl = "about:newtab"
    
        if isinstance(qurl, str):
            s = qurl.strip()
            ls = s.lower()
    
            # 1) домашняя/новая вкладка
            if ls in ("about:newtab", "newtab:/", "home:/", "salem:/home"):
                webview = _new_view()
                home = getattr(self, "home_url", None) or "http://127.0.0.1:5000/"
                webview.setUrl(QUrl(home))
                idx = self.tabs.addTab(webview, "Новая вкладка")
                self.tabs.setCurrentIndex(idx)
                self.tabs.tabBar().setTabData(idx, {"pinned": False})
                _post_add(webview, idx)
    
                # маскировка заголовка, если это home
                webview.loadFinished.connect(
                    lambda ok, sv=webview, i=idx:
                        (self.tabs.setTabText(i, "Новая вкладка")
                         if ok and getattr(self, "_is_home_url", lambda *_: False)(sv.url()) else None)
                )
                return webview
    
            # 2) загрузки
            if ls in ("about:downloads", "downloads:/", "app://downloads",
                      "configure:/downloads", "downloads:", "app:/downloads"):
                return self.open_downloads_tab()
    
            # 3) моды
            if ls in ("salem://mods", "salem:/mods", "about:mods",
                      "configure:/mods", "configure://mods"):
                fn = getattr(self, "open_mods_manager_tab", None)
                if callable(fn):
                    return fn()
                if ModManager is not None and getattr(self, "mod_loader", None) is not None:
                    for i in range(self.tabs.count()):
                        if isinstance(self.tabs.widget(i), ModManager):
                            self.tabs.setCurrentIndex(i)
                            return self.tabs.widget(i)
                    w = ModManager(self.mod_loader, parent=self, as_page=True)
                    idx = self.tabs.addTab(w, "Моды")
                    self.tabs.setCurrentIndex(idx)
                    self.tabs.tabBar().setTabData(idx, {"pinned": False})
                    return w
                return None
    
            # 4) расширения
            if ls in ("ext://extensions", "ext:/extensions", "ext:extensions",
                      "configure:/extensions", "configure://extensions"):
                if ExtensionManager is not None:
                    for i in range(self.tabs.count()):
                        if isinstance(self.tabs.widget(i), ExtensionManager):
                            self.tabs.setCurrentIndex(i)
                            return self.tabs.widget(i)
                    w = ExtensionManager(getattr(self, "extension_loader", None), parent=self, as_page=True)
                    idx = self.tabs.addTab(w, "Расширения")
                    self.tabs.setCurrentIndex(idx)
                    self.tabs.tabBar().setTabData(idx, {"pinned": False})
                    return w
                return None
    
            # 5) история
            if ls in ("hist://history", "app://history", "configure:/history", "history:/", "app:/history"):
                if getattr(self, "history_panel", None) is None and HistoryPanel is not None:
                    try:
                        self.history_panel = HistoryPanel(open_callback=self._navigate_to_url, parent=self)
                    except Exception:
                        self.history_panel = None
                if getattr(self, "history_panel", None) is not None:
                    for i in range(self.tabs.count()):
                        if self.tabs.widget(i) is self.history_panel:
                            self.tabs.setCurrentIndex(i)
                            return self.history_panel
                    idx = self.tabs.addTab(self.history_panel, "История")
                    self.tabs.setCurrentIndex(idx)
                    self.tabs.tabBar().setTabData(idx, {"pinned": False})
                    return self.history_panel
                return None
    
            # 6) configure://...
            if ls.startswith(("configure:/", "configure://")):
                scheme, target, params = self._parse_internal_url(qurl)
    
                # пусто или sidebar => открыть панель
                if not target or target == "sidebar":
                    try: self.settings_panel.show_settings("Настройки")
                    except Exception: pass
                    return None
    
                if target in ("downloads", "загрузки"):
                    return self.open_downloads_tab()
                if target in ("history", "история"):
                    return self.open_history_tab()
                if target in ("extensions", "ext", "расширения"):
                    return self.add_new_tab("ext://extensions")
                if target in ("mods", "моды"):
                    return self.add_new_tab("salem://mods")
    
                if target in ("accent", "акцент", "color"):
                    hx = params.get("hex") or params.get("color")
                    if hx:
                        try: self.settings_panel._set_accent(hx)
                        except Exception: pass
                    try: self.settings_panel.show_settings("Настройки")
                    except Exception: pass
                    return None
    
                if target in ("font", "шрифт"):
                    fam = params.get("ui") or params.get("family") or params.get("font")
                    if fam:
                        try: self.settings_panel._set_font(fam)
                        except Exception: pass
                    try: self.settings_panel.show_settings("Настройки")
                    except Exception: pass
                    return None
    
                try: self.settings_panel.show_settings("Настройки")
                except Exception: pass
                return None
    
        # 7) готовый QWidget — просто добавим как вкладку
        if hasattr(qurl, "setParent") and hasattr(qurl, "objectName"):
            w = qurl
            idx = self.tabs.addTab(w, label or getattr(w, "windowTitle", lambda: "")() or "Страница")
            self.tabs.setCurrentIndex(idx)
            self.tabs.tabBar().setTabData(idx, {"pinned": False})
            return w
    
        # ───────── обычная веб-вкладка ─────────
        webview = _new_view()
    
        # URL по умолчанию
        if not qurl:
            qurl = getattr(self, "home_url", None) or "http://127.0.0.1:5000/"
        real_url = qurl if isinstance(qurl, QUrl) else QUrl(str(qurl))
        webview.setUrl(real_url)
    
        idx = self.tabs.addTab(webview, label)
        self.tabs.setCurrentIndex(idx)
        self.tabs.tabBar().setTabData(idx, {"pinned": False})
        _post_add(webview, idx)
    
        return webview




    def _find_extensions_tab(self):
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), ExtensionManager):
                return i
        return -1

    def open_extensions_manager_tab(self):
        idx = self._find_extensions_tab()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
            return
        # используем унифицированный путь через add_new_tab
        self.add_new_tab("ext://extensions", "Расширения")

    def _find_mods_tab(self):
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), ModManager):
                return i
        return -1

    def open_mods_manager_tab(self):
            idx = self._find_mods_tab()
            if idx >= 0:
                self.tabs.setCurrentIndex(idx); return
            w = ModManager(self.mod_loader, parent=self, as_page=True)
            i = self.tabs.addTab(w, "Моды")
            self.tabs.setCurrentIndex(i)

    def _register_webview(self, webview):
        page = webview.page()

        # расширения
        try:
            self.extension_loader.attach(webview)
        except Exception as e:
            print('[EXT] attach failed:', e)

        try:
            self.mod_loader.attach(webview)
        except Exception as e:
            print('[MODS] attach failed:', e)


        # маппинг page→view
        self._page_to_view[id(page)] = weakref.ref(webview)
        def _drop(_=None, pid=id(page)): self._page_to_view.pop(pid, None)
        webview.destroyed.connect(_drop); page.destroyed.connect(_drop)

        # PiP
        self.inject_pip_button(webview)
        webview.loadFinished.connect(lambda: self.inject_pip_button(webview))
        self.setup_pip_handler(webview)

        # fullscreen
        page.fullScreenRequested.connect(lambda req, v=webview: self.handle_video_fullscreen_request(req, v))

        # 🔊 аудио-интеграция с таббаром: индекс вычисляем на момент события
        bar = getattr(self.tabs, "tabBar", lambda: None)()
        if bar and hasattr(bar, "set_tab_audio_state"):
            def _idx():  # динамический индекс; если вкладку перетаскивали — будет актуально
                try: return self.tabs.indexOf(webview)
                except Exception: return -1

            if hasattr(page, "recentlyAudibleChanged"):
                page.recentlyAudibleChanged.connect(
                    lambda audible: (_ := _idx()) >= 0 and bar.set_tab_audio_state(_, bool(audible),
                        page.isAudioMuted() if hasattr(page, "isAudioMuted") else None)
                )

            if hasattr(page, "audioMutedChanged"):
                page.audioMutedChanged.connect(
                    lambda muted: (_ := _idx()) >= 0 and bar.set_tab_muted(_, bool(muted))
                )



    def toggle_window_fullscreen(self):
        """Переключение полноэкранного режима всего окна браузера."""
        # Если открыт PiP – не трогаем всё приложение
        if getattr(self, "pip_window", None) and self.pip_window.isVisible():
            return
        self.showNormal() if self.isFullScreen() else self.showFullScreen()


    def handle_video_fullscreen_request(self, request, view):
        try:
            # Безопасно принять запрос
            request.accept()
        except Exception as e:
            print("[fullscreen] accept error:", e)
            return

        # Получаем страницу, откуда пришёл запрос
        page = self.sender()
        vref = self._page_to_view.get(id(page))
        view = vref() if vref else None

        if view is None or sip.isdeleted(view):
            print("[fullscreen] view is None or deleted")
            return

        toggle_on = False
        try:
            toggle_on = bool(request.toggleOn())
        except Exception as e:
            print("[fullscreen] toggleOn error:", e)

        if toggle_on:
            # Сохраняем текущее состояние окна
            self._prev_geometry = self.geometry()
            self._prev_flags = self.windowFlags()

            # Переводим текущее видео в полноэкранный контейнер
            self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.showFullScreen()
            view.showFullScreen()
            print("[fullscreen] enabled")
        else:
            # Выход из fullscreen — возвращаем всё на место
            try:
                view.showNormal()
            except Exception:
                pass

            if hasattr(self, "_prev_flags"):
                self.setWindowFlags(self._prev_flags)
            self.showNormal()

            if hasattr(self, "_prev_geometry"):
                self.setGeometry(self._prev_geometry)

            print("[fullscreen] disabled")

        # PiP-режим — отдельный случай, его не трогаем
        if hasattr(self, "pip_window") and self.pip_window:
            pip = self.pip_window
            if toggle_on:
                if pip._view is not view:
                    pip.adopt_view(view)
                    pip.show()
                pip._set_local_fs(True)
            else:
                if pip._view is view:
                    pip._set_local_fs(False)




    def _ensure_pip_window(self):
        if not hasattr(self, "pip_window") or self.pip_window is None:
            self.pip_window = PipWindow(self)
            self.pip_window.closed.connect(self._restore_from_pip)  # твой хендлер
        return self.pip_window

    def _reinsert_webview_to_current_tab(self, view: QWebEngineView):
        """
        Возвращает webview из PiP обратно в текущую вкладку.
        Если вкладка — чистый QWebEngineView, вставляем напрямую.
        Если вкладка обёрнута в QWidget+layout — поддержим и это.
        """
        if view is None:
            return

        current = self.tabs.currentWidget()

        # 🔹 Случай 1: вкладка — чистый QWebEngineView
        if isinstance(current, QWebEngineView):
            idx = self.tabs.currentIndex()
            self.tabs.removeTab(idx)
            i = self.tabs.insertTab(idx, view, view.title())
            self.tabs.setCurrentIndex(i)
            return

        # 🔹 Случай 2: вкладка — контейнер с layout
        if isinstance(current, QWidget) and current.layout() is not None:
            lay = current.layout()
            lay.addWidget(view)
            view.show()
            return

        # 🔹 Фоллбэк: просто добавим новую вкладку
        i = self.tabs.addTab(view, view.title() or "Tab")
        self.tabs.setCurrentIndex(i)

        icon = view.icon() if hasattr(view, "icon") else None
        title = view.title() or "Tab"

        i = self.tabs.addTab(view, title)
        if icon:
            self.tabs.setTabIcon(i, icon)
        self.tabs.setCurrentIndex(i)






    def create_nav_button(self, text, callback):
        button = QPushButton(text)
        button.setFixedSize(90, 25)   # или 40, 25 если хочешь меньше
        button.clicked.connect(callback)
        return button
    
    def downloads_btn(self):
        """Открывает панель загрузок."""
        if not self.downloads_panel.isVisible():
            self.downloads_panel.show()
        else:
            self.downloads_panel.activateWindow()
            self.downloads_panel.raise_()


    def navigate_home(self):
        """Переход на домашнюю страницу без дублирования вкладок."""
        from PyQt5.QtCore import QUrl

        try:
            self.url_bar.blockSignals(True)
            self.url_bar.clear()
            self.url_bar.setPlaceholderText("Новая вкладка — введите запрос или адрес")
            self.url_bar.setCursorPosition(0)
        finally:
            self.url_bar.blockSignals(False)

        target_url = self.home_url or "http://127.0.0.1:5000/"
        cur = self.tabs.currentWidget()

        if isinstance(cur, QWebEngineView):
            # если уже на home — ничего не делаем
            if self._is_home_url(cur.url()):
                return
            cur.setUrl(QUrl(target_url))
        else:
            # если вкладок нет — открыть, иначе переключиться на первую
            if self.tabs.count() == 0:
                self.add_new_tab(target_url, "Жаңа бет")
            else:
                self.tabs.setCurrentIndex(0)



        # ——— URL utils ———
    def _url_str(self, url) -> str:
        try:
            from PyQt5.QtCore import QUrl
            return url.toString() if isinstance(url, QUrl) else str(url or "")
        except Exception:
            return str(url or "")

    def _is_home_url(self, url) -> bool:
        """True, если это наш «дом» (root UI страницы на локальном сервере)."""
        from PyQt5.QtCore import QUrl
        try:
            u = QUrl(self._url_str(url))
            base = QUrl(self.home_url or "http://127.0.0.1:5000/")
            if not u.isValid() or not base.isValid():
                return False

            same_host = (
                u.scheme().lower() == base.scheme().lower()
                and u.host().lower() == base.host().lower()
                and (u.port() or (443 if u.scheme().lower()=="https" else 80))
                    == (base.port() or (443 if base.scheme().lower()=="https" else 80))
            )
            if not same_host:
                return False

            # нормализуем путь
            path = (u.path() or "/").rstrip("/") or "/"

            # признаём домашними: "/", "/ui", "/index.html"
            return path in ("/", "/ui", "/index.html")
        except Exception:
            return False


    def _on_urlbar_enter(self):
        text = self.url_bar.text().strip()
        if not text:
            return
        # Дай шанс внутренним схемам и "голым" доменам
        self._navigate_to_url(text)


    def _navigate_to_url(self, url: str):
        """Безопасная навигация из HistoryPanel и других виджетов."""
        if not url:
            return
        try:
            self.url_bar.setText(str(url))
        except Exception:
            pass

        u = str(url).strip().lower()
        if u in ("salem://mods", "about:mods"):
            self.open_mods_manager_tab()
            return

        # если текущая вкладка — WebView, навигируем напрямую
        cur = getattr(self.tabs, "currentWidget", lambda: None)()
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            from PyQt5.QtCore import QUrl
            if isinstance(cur, QWebEngineView):
                cur.setUrl(QUrl(url))
                return
        except Exception:
            pass
        # fallback: стандартный обработчик
        self.navigate_to_url()
        
    def open_extensions_manager_tab(self):
        """Открывает менеджер расширений как лёгкую вкладку и загружает данные в фоне."""
        # 1) Если уже открыта — просто переключиться
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), ExtensionManager):
                self.tabs.setCurrentIndex(i)
                return self.tabs.widget(i)

        # 2) Создаём пустой менеджер (as_page=True у тебя уже стоит)
        manager = ExtensionManager(self.extension_loader, parent=self, as_page=True)
        idx = self.tabs.addTab(manager, "Расширения")
        self.tabs.setCurrentIndex(idx)

        # 3) Если у менеджера есть свой async-метод — используем его
        for meth in ("load_async", "scan_async", "reload_async"):
            fn = getattr(manager, meth, None)
            if callable(fn):
                # стартуем по следующему обороту цикла событий — UI успеет отрисоваться
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0, fn)
                return manager

        # 4) Иначе — наш фоновой воркер. Важно: НИЧЕГО тяжёлого не делать до запуска потока.
        # Покажем спиннер/плейсхолдер, если в менеджере есть метод-поддержка
        show_busy = getattr(manager, "show_busy", None)
        if callable(show_busy):
            try: show_busy(True)
            except Exception: pass

        thr = QThread(self)
        worker = _ExtScanWorker(self.extension_loader)
        worker.moveToThread(thr)

        def _on_done(data):
            # Сюда вернулись с результатами — обновляем UI только в GUI-потоке
            apply_fn = getattr(manager, "apply_scan_results", None) or getattr(manager, "set_items", None)
            if callable(apply_fn):
                try: apply_fn(data)
                except Exception: pass
            # Убираем индикатор
            if callable(show_busy):
                try: show_busy(False)
                except Exception: pass
            thr.quit(); thr.wait()

        def _on_err(msg):
            print("[extensions] scan failed:", msg)

        worker.finished.connect(_on_done)
        worker.error.connect(_on_err)
        thr.started.connect(worker.run)
        thr.start()
        return manager



    def open_extensions_window(self):
        """Первый клик по кнопке расширений: открыть мини-попап, второй — вкладку."""
        try:
            anchor = self.extensions_btn
        except Exception:
            anchor = self.sender()

        if self.ext_popup is None:
            self.ext_popup = ExtensionsMiniPopup(
                self,
                self.extension_loader,
                open_full_callback=self.open_extensions_manager_tab  # теперь всегда во вкладке
            )

        if self.ext_popup.isVisible():
            self.ext_popup.close()
        else:
            self.ext_popup.open_at(anchor)


    def open_extensions_manager(self):
        """Для совместимости: всегда вызывает open_extensions_manager_tab."""
        return self.open_extensions_manager_tab()




    def open_file(self):
        """Открывает диалог выбора файла и загружает его в новую вкладку."""
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Файлды ашу", "", "Барлық файлдар (*.*);;PDF файлдары (*.pdf);;HTML файлдары (*.html);;XML файлдары (*.xml);;YAML файлдары (*.yaml *.yml);;CSS файлдары (*.css);;JavaScript файлдары (*.js);;TypeScript файлдары (*.ts)",
            options=options
        )
        if not file_path:
            return

        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension == ".pdf":
            self.add_new_tab(QUrl.fromLocalFile(file_path), f"PDF: {os.path.basename(file_path)}")
        elif file_extension in [".html", ".xml", ".yaml", ".yml", ".css", ".js", ".ts"]:
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
            text_editor = QPlainTextEdit()
            text_editor.setPlainText(content)
            text_editor.setReadOnly(True)
            index = self.tabs.addTab(text_editor, f"Файл: {os.path.basename(file_path)}")
            self.tabs.setCurrentIndex(index)
        else:
            print("⚠ Файл форматы қолдау көрсетілмейді!")

    def next_tab(self):
        """Переключиться на следующую вкладку."""
        idx = self.tabs.currentIndex()
        count = self.tabs.count()
        if count > 0:
            self.tabs.setCurrentIndex((idx + 1) % count)

    def prev_tab(self):
        """Переключиться на предыдущую вкладку."""
        idx = self.tabs.currentIndex()
        count = self.tabs.count()
        if count > 0:
            self.tabs.setCurrentIndex((idx - 1) % count)




    def close_current_tab(self, index):
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)


    def navigate_back(self):
        current = self.tabs.currentWidget()
        if current:
            current.back()


    def navigate_forward(self):
        current = self.tabs.currentWidget()
        if current:
            current.forward()


    def refresh_page(self):
        current = self.tabs.currentWidget()
        if not current:
            return

        # 1) Обычная веб-страница
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            if isinstance(current, QWebEngineView):
                current.reload()
                return
        except Exception:
            pass

        # 2) Сервисные вкладки (История, Расширения, Моды и т.п.)
        for name in ("reload", "_reload", "refresh", "reload_list", "rebuild", "update"):
            fn = getattr(current, name, None)
            if callable(fn):
                try:
                    fn()
                except TypeError:
                    try:
                        fn(False)
                    except Exception:
                        pass
                return

        # 3) Фолбэк — просто перерисовать
        try:
            current.repaint()
            current.update()
        except Exception:
            pass



    def open_devtools_tab(self):  # кнопка 🛠
        self.toggle_devtools()

    def open_dev_tools(self):     # пункт меню
        self.toggle_devtools()

    def toggle_devtools(self):
        """Показать/скрыть правую док-панель DevTools."""
        if not hasattr(self, "devtools"):
            return

        view = self.tabs.currentWidget()
        if isinstance(view, QWebEngineView):
            try:
                self.devtools.attach(view)   # ключевая строка
            except Exception as e:
                print(f"[DevTools] attach() failed: {e}")

        try:
            self.devtools.toggle()
            return
        except AttributeError:
            # Фолбэк (на случай, если у класса нет toggle)
            vis = getattr(self.devtools, "isVisible", lambda: None)
            if callable(vis) and vis():
                getattr(self.devtools, "hide", lambda: None)()
            else:
                getattr(self.devtools, "show", lambda: None)()



    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress and not event.isAutoRepeat():
            if event.key() == Qt.Key_F12:
                self.toggle_devtools(); return True
            if event.key() == Qt.Key_U and (event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier)):
                self.view_page_source(); return True
        return super().eventFilter(obj, event)




    def handle_download_request(self, download):
        suggested_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить файл", download.path(), "All Files (*.*)"
        )
        if suggested_path:
            download.setPath(suggested_path)
            download.accept()
            self.downloads_panel.add_download(download.url().toString(), suggested_path)
            self.downloads_panel.show()
        else:
            download.cancel()



    def update_downloads(self, file_path):
        self.downloads_panel.addItem(f"Жүктелді: {file_path}")



    def save_page(self):
        current_browser = self.tabs.currentWidget()
        if current_browser:
            file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить страницу как", "", "HTML файлы (*.html);;Все файлы (*.*)")
            if file_path:
                current_browser.page().toHtml(lambda html: open(file_path, "w", encoding="utf-8").write(html))

    def save_image(self, data):
        url = data.mediaUrl()
        if not (url and url.isValid()):
            return
        suggested = url.fileName() or "image"
        default_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        os.makedirs(default_dir, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить изображение", os.path.join(default_dir, suggested),
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp);;All files (*.*)"
        )
        if not path:
            return
        # чтобы глобальный диалог в handle_download_request НЕ всплывал второй раз
        self._suppress_download_dialog = True
        # прямой заказ скачивания на профиль с уже выбранным путём
        self.profile.download(QUrl(url), path)




    def open_menu(self):
        if not hasattr(self, "settings_panel"):
            # На всякий, но по-хорошему создаётся в __init__
            from modules.salem_sidebar import SettingsSidebar
            self.settings_panel = SettingsSidebar(self, asset_resolver=getattr(self, "_asset", None))
            self.settings_panel.set_profile(self.profile)


        # Обёртка: сначала спрячем панель, потом выполним действие
        def _wrap(cb):
            def _inner():
                try:
                    # чуть-чуть подождём, чтобы анимация закрытия не лагала
                    from PyQt5.QtCore import QTimer
                    self.settings_panel.hide_with_anim()
                    QTimer.singleShot(120, cb)
                except Exception:
                    cb()
            return _inner

        actions = [
            ("Жаңа қойынды",                     _wrap(lambda: self.add_new_tab()),               "img/icons/new-tab.svg"),
            ("AI Чат (Messenger)",               _wrap(self.open_chatgpt_dock),                   "img/icons/chat.svg"),
            ("Пайдаланушы тіркелгісі",           _wrap(self.enable_user_account),                 "img/icons/user.svg"),
            ("Әзірлеуші режимі",                 _wrap(self.open_devtools_tab),                   "img/icons/app-window.svg"),
            ("Picture-in-Picture (PiP) режимі", _wrap(self.menu_pip_mode),                        "img/icons/pip.svg"),
            ("SalemMedia Player",                _wrap(self.open_media_tab),                      "img/icons/player.svg"),
            ("Бетбелгілер",                      _wrap(self.bookmarks_bar.toggle),                "img/icons/bookmarks.svg"),
            ("Жаңа терезе",                      _wrap(self.open_new_window),                     "img/icons/window-new.svg"),
            ("Жаңа құпия терезе",                _wrap(self.open_incognito_window),               "img/icons/spy.svg"),
            ("Журнал",                           _wrap(self.open_history_tab),                        "img/icons/history.svg"),
            ("Құпиясөздер",                      _wrap(self.manage_passwords),                    "img/icons/lock.svg"),
            ("Қосымшалар мен тақырыптар", _wrap(self.open_extensions_manager_tab), "img/icons/puzzle.svg"),
            ("Басып шығару",                     _wrap(self.print_page),                          "img/icons/print.svg"),
            ("Қалай сақтау",                     _wrap(self.save_page),                           "img/icons/save.svg"),
            ("Экран масштабы",                   _wrap(self.zoom_menu),                           "img/icons/zoom1.svg"),
            ("Баптаулар",                        _wrap(lambda: self.settings_panel.show_settings("Баптаулар")), "img/icons/settings.svg"),
            ("Шығу",                             _wrap(self.safe_exit),                           "img/icons/power.svg"),
        ]

        self.settings_panel.show_menu(actions, title="Меню Salem")

    def open_settings(self):
        if hasattr(self, "settings_panel"):
            self.settings_panel.show_settings("Баптаулар")



    def enable_user_account(self):
        base = os.path.dirname(os.path.abspath(__file__))
        local_path = os.path.join(base, "templates", "UserAccount.html")
        url = QUrl.fromLocalFile(local_path)
    
        view = self.add_new_tab(url, "Salem Account")  # должен вернуть QWebEngineView
        if view is None:
            print(" Вкладка не создана"); return
    
        page = view.page()
        channel = QWebChannel(page)
        self.account_bridge = AccountBridge(base_dir=base)  # фиксируем ссылку, чтобы GC не съел
        channel.registerObject('SalemBridge', self.account_bridge)
        page.setWebChannel(channel)

    def user_account_btn(self):
        local_path = os.path.abspath("templates/UserAccount.html")
        url = QUrl.fromLocalFile(local_path)
        self.add_new_tab(url, "Salem Account")

    def open_media_tab(self):
        from PyQt5.QtCore import QUrl
        self.add_new_tab(QUrl("http://127.0.0.1:7000/ui"), "Media")


    def _restore_from_pip(self):
        if not self._pip_state:
            if self.pip_window:
                self.pip_window.close()
                self.pip_window = None
            return
    
        view  = self._pip_state["view"]
        idx   = max(0, min(self._pip_state["index"], self.tabs.count()))
        label = self._pip_state["label"]
        icon  = self._pip_state["icon"]
    
        if self.pip_window:
            try: self.pip_window.closed.disconnect(self._restore_from_pip)
            except Exception: pass
            self.pip_window.release_view()
            self.pip_window.close()
            self.pip_window = None
    
        i = self.tabs.insertTab(idx, view, label)
        if icon: self.tabs.setTabIcon(i, icon)
        self.tabs.setCurrentIndex(i)
        self._pip_state = None

    def _ensure_history_panel(self):
        """Создаёт self.history_panel, если её ещё нет (без добавления во вкладки)."""
        if getattr(self, "history_panel", None) is None:
            try:
                from modules.history_ui import HistoryPanel
                self.history_panel = HistoryPanel(open_callback=self._navigate_to_url, parent=self)
            except Exception as e:
                print("[history] create panel failed:", e)
                self.history_panel = None

    def _find_history_tab(self) -> int:
        """Возвращает индекс вкладки с HistoryPanel или -1."""
        try:
            if not hasattr(self, "tabs") or self.tabs is None:
                return -1
        except Exception:
            return -1
        panel = getattr(self, "history_panel", None)
        if panel is None:
            return -1
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) is panel:
                return i
        return -1
    
    def open_history_tab(self):
        # Если панель истории ещё не создана — создаём
        if not hasattr(self, "history_panel") or self.history_panel is None:
            from modules.history_ui import HistoryPanel
            self.history_panel = HistoryPanel(open_callback=self._navigate_to_url, parent=self)
            idx = self.tabs.addTab(self.history_panel, "История")
            self.tabs.setCurrentIndex(idx)
            return

        # Если уже есть — просто активируем вкладку
        idx = self.tabs.indexOf(self.history_panel)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)
        else:
            idx = self.tabs.addTab(self.history_panel, "История")
            self.tabs.setCurrentIndex(idx)

    def open_new_window(self):
        new_window = SalemBrowser()
        new_window.show()


    def open_incognito_window(self):
        new_incognito = SalemBrowser()
        new_incognito.show()

    # рядом с open_history_tab:
    def _find_downloads_tab(self) -> int:
        if not hasattr(self, "tabs") or self.tabs is None:
            return -1
        panel = getattr(self, "downloads_panel", None)
        if panel is None:
            return -1
        for i in range(self.tabs.count()):
            if self.tabs.widget(i) is panel:
                return i
        return -1

    def open_downloads_tab(self):
        if not hasattr(self, "tabs") or self.tabs is None:
            print("[downloads] tabs not ready yet"); return
        # гарантируем, что панель есть и подключена к профилю
        if getattr(self, "downloads_panel", None) is None:
            self.downloads_panel = DownloadsPanel()
            try:
                self.profile.downloadRequested.connect(self.downloads_panel.handle_download)
            except Exception:
                pass
        idx = self._find_downloads_tab()
        if idx >= 0:
            self.tabs.setCurrentIndex(idx); return
        i = self.tabs.addTab(self.downloads_panel, "Загрузки")
        self.tabs.setCurrentIndex(i)

    def print_page(self):
        current = self.tabs.currentWidget()
        if current:
            current.page().printToPdf("saved_page.jpg")

    def manage_passwords(self):
        local_path = os.path.abspath("templates/UserAccount.html")
        url = QUrl.fromLocalFile(local_path)
        self.add_new_tab(url, "Salem Account")


    def search_on_page(self):
        text, ok = QInputDialog.getText(self, "Іздеу", "Іздеу мәтінін енгізіңіз:")
        if ok and text:
            current = self.tabs.currentWidget()
            if current:
                current.findText(text)


    def open_settings(self):
        self.add_new_tab(QUrl("http://127.0.0.1:1442/settings/"), "Баптаулар")


    def open_help(self):
        self.add_new_tab(QUrl("http://127.0.0.1:1221/support"), "Анықтама")


    def zoom_menu(self):
        zoom_levels = ["50%", "75%", "100%", "125%", "150%", "200%"]
        zoom, ok = QInputDialog.getItem(self, "Масштаб", "Таңдаңыз:", zoom_levels, 2, False)
        if ok:
            scale = int(zoom.replace("%", "")) / 100
            current = self.tabs.currentWidget()
            if current:
                current.setZoomFactor(scale)


    def open_file(self):
        options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Файлды ашу",
            "",
            "Все поддерживаемые файлы (*.pdf *.html *.xml *.yaml *.yml *.css *.js *.ts *.json *.txt *.md *.csv *.log *.svg "
            "*.png *.jpg *.jpeg *.gif *.bmp *.webp *.mp4 *.avi *.mov *.webm *.mkv *.mp3 *.wav *.flac *.ogg);;"
            "PDF файлы (*.pdf);;HTML (*.html);;XML (*.xml);;YAML (*.yaml *.yml);;CSS (*.css);;"
            "JavaScript (*.js);;TypeScript (*.ts);;JSON (*.json);;Текст (*.txt *.md *.csv *.log *.svg);;"
            "Изображения (*.png *.jpg *.jpeg *.gif *.bmp *.webp *.svg);;"
            "Аудио (*.mp3 *.wav *.flac *.ogg);;Видео (*.mp4 *.avi *.mov *.webm *.mkv)",
            options=options
        )
        if not file_path:
            return
    
        file_extension = os.path.splitext(file_path)[1].lower()
        filename = os.path.basename(file_path)
    
        # PDF, HTML, XML — WebView (просмотр)
        if file_extension in [".pdf", ".html", ".xml"]:
            webview = QWebEngineView()
            webview.setUrl(QUrl.fromLocalFile(file_path))
            idx = self.tabs.addTab(webview, f"{file_extension.upper()[1:]}: {filename}")
            self.tabs.setCurrentIndex(idx)
            return
    
        # Текстовые файлы (JSON, TXT, MD, CSV, LOG, YAML, YML, CSS, JS, TS, SVG)
        elif file_extension in [".json", ".txt", ".md", ".csv", ".log", ".yaml", ".yml", ".css", ".js", ".ts", ".svg"]:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                with open(file_path, "r", encoding="cp1251", errors="ignore") as f:
                    content = f.read()
            text_editor = QPlainTextEdit()
            text_editor.setPlainText(content)
            text_editor.setReadOnly(True)
            text_editor.setLineWrapMode(QPlainTextEdit.NoWrap)
            idx = self.tabs.addTab(text_editor, f"{file_extension.upper()[1:]}: {filename}")
            self.tabs.setCurrentIndex(idx)
            return
    
        # Картинки (PNG, JPG, JPEG, GIF, BMP, WEBP, SVG)
        elif file_extension in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"]:
            pixmap = QPixmap(file_path)
            if pixmap.isNull():
                QMessageBox.critical(self, "Ошибка", "Не удалось загрузить изображение")
                return
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            idx = self.tabs.addTab(label, f"IMG: {filename}")
            self.tabs.setCurrentIndex(idx)
            return
    
        # Видео
        elif file_extension in [".mp4", ".avi", ".mov", ".webm", ".mkv"]:
            from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
            from PyQt5.QtMultimediaWidgets import QVideoWidget
            video_player = QMediaPlayer()
            video_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            video_widget = QVideoWidget()
            video_player.setVideoOutput(video_widget)
            video_player.play()
            idx = self.tabs.addTab(video_widget, f"Видео: {filename}")
            self.tabs.setCurrentIndex(idx)
            return
    
        # Аудио
        elif file_extension in [".mp3", ".wav", ".flac", ".ogg"]:
            from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
            audio_player = QMediaPlayer()
            audio_player.setMedia(QMediaContent(QUrl.fromLocalFile(file_path)))
            audio_player.play()
            label = QLabel(f"Аудио: {filename}")
            idx = self.tabs.addTab(label, f"Аудио: {filename}")
            self.tabs.setCurrentIndex(idx)
            return
    
        else:
            QMessageBox.warning(self, "Формат не поддерживается", f"Файл {filename} не поддерживается!")



if __name__ == "__main__":
    app = QApplication(sys.argv)
    browser = SalemBrowser()
    browser.show()
    sys.exit(app.exec_())


