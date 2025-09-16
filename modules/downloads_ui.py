from __future__ import annotations
import os
import json
import time
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Callable

from PyQt5.QtCore import Qt, QSize, QStandardPaths, QTimer
from PyQt5.QtGui import QIcon, QCursor, QColor, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QFileDialog,
    QMessageBox, QListWidget, QListWidgetItem, QLineEdit, QComboBox, QToolButton, QMenu,
    QStyle, QShortcut, QAbstractItemView
)
from PyQt5.QtWebEngineWidgets import QWebEngineDownloadItem

# ---------- Хранилище ----------

APP_DIR = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.path.join(os.path.expanduser("~"), ".salem")
os.makedirs(APP_DIR, exist_ok=True)
DOWNLOADS_JSON = os.path.join(APP_DIR, "downloads_history.json")

# ---------- Модель ----------

@dataclass
class DownloadEntry:
    uid: str
    url: str
    filename: str
    path: str
    status: str              # "Загрузка" | "Готово" | "Ошибка" | "Отменено"
    date: str                # iso datetime string
    progress: int = 0        # 0..100
    bytes_received: int = 0
    bytes_total: int = 0
    mime_type: str = ""
    error_string: str = ""
    # runtime-only (не пишем в JSON)
    _runtime: dict = field(default_factory=dict, repr=False, compare=False)

    def to_json(self):
        d = asdict(self)
        d.pop("_runtime", None)
        return d

    @staticmethod
    def from_json(d: dict) -> 'DownloadEntry':
        return DownloadEntry(
            uid=d.get("uid", ""),
            url=d.get("url", ""),
            filename=d.get("filename", ""),
            path=d.get("path", ""),
            status=d.get("status", "Готово"),
            date=d.get("date", ""),
            progress=int(d.get("progress", 0)),
            bytes_received=int(d.get("bytes_received", 0)),
            bytes_total=int(d.get("bytes_total", 0)),
            mime_type=d.get("mime_type", ""),
            error_string=d.get("error_string", ""),
        )

# ---------- Утилиты ----------

def _human_size(n: int) -> str:
    if n is None:
        return ""
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f} {u}"
        f /= 1024.0
    return f"{f:.1f} PB"

def _human_eta(left_bytes: int, speed_bps: float) -> str:
    if speed_bps <= 1e-6 or left_bytes <= 0:
        return "—"
    sec = int(left_bytes / max(speed_bps, 1))
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h: return f"{h}ч {m}м"
    if m: return f"{m}м {s}с"
    return f"{s}с"

def _file_icon_for(path_or_name: str, style) -> QIcon:
    ext = os.path.splitext(path_or_name)[1].lower()
    # Пробуем подобрать системные иконки
    if ext in {".zip", ".7z", ".rar"}:
        return style.standardIcon(QStyle.SP_DirIcon)
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return style.standardIcon(QStyle.SP_FileIcon)
    if ext in {".mp4", ".mkv", ".avi", ".mov"}:
        return style.standardIcon(QStyle.SP_MediaPlay)
    if ext in {".mp3", ".wav", ".flac"}:
        return style.standardIcon(QStyle.SP_MediaVolume)
    if ext in {".pdf"}:
        return style.standardIcon(QStyle.SP_DialogHelpButton)
    return style.standardIcon(QStyle.SP_FileIcon)

# ---------- Виджет строки ----------

class _RowWidget(QWidget):
    def __init__(self, panel: 'DownloadsPanel', entry: DownloadEntry):
        super().__init__(panel)
        self.panel = panel
        self.entry = entry
        self.setObjectName("dlRow")

        icon_lbl = QLabel()
        icon_lbl.setPixmap(_file_icon_for(entry.filename or entry.path, self.style()).pixmap(24, 24))
        icon_lbl.setFixedSize(28, 28)

        self.title_lbl = QLabel(entry.filename or "—")
        self.title_lbl.setObjectName("dlTitle")
        self.sub_lbl = QLabel(self._build_subtitle())
        self.sub_lbl.setObjectName("dlSub")
        self.sub_lbl.setTextFormat(Qt.RichText)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(entry.progress or 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)

        # Кнопки действий
        self.btn_pause = QToolButton(self); self.btn_pause.setText("Пауза")
        self.btn_resume = QToolButton(self); self.btn_resume.setText("Продолжить")
        self.btn_cancel = QToolButton(self); self.btn_cancel.setText("Отмена")
        self.btn_open = QToolButton(self); self.btn_open.setText("Открыть")
        self.btn_folder = QToolButton(self); self.btn_folder.setText("Папка")
        self.btn_retry = QToolButton(self); self.btn_retry.setText("Повторить")

        # Подключения
        self.btn_pause.clicked.connect(lambda: panel._pause(self.entry.uid))
        self.btn_resume.clicked.connect(lambda: panel._resume(self.entry.uid))
        self.btn_cancel.clicked.connect(lambda: panel._cancel(self.entry.uid))
        self.btn_open.clicked.connect(lambda: panel._open_file(self.entry.uid))
        self.btn_folder.clicked.connect(lambda: panel._show_in_folder(self.entry.uid))
        self.btn_retry.clicked.connect(lambda: panel._retry(self.entry.uid))

        # Лэйаут
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(8)
        head.addWidget(icon_lbl)
        name_col = QVBoxLayout()
        name_col.setContentsMargins(0, 0, 0, 0)
        name_col.setSpacing(2)
        name_col.addWidget(self.title_lbl)
        name_col.addWidget(self.sub_lbl)
        head.addLayout(name_col, 1)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(6)
        btns.addWidget(self.btn_pause)
        btns.addWidget(self.btn_resume)
        btns.addWidget(self.btn_cancel)
        btns.addWidget(self.btn_open)
        btns.addWidget(self.btn_folder)
        btns.addWidget(self.btn_retry)

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)
        root.addLayout(head)
        root.addWidget(self.progress)
        root.addLayout(btns)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda _: self._context_menu())

        self._refresh_buttons()

    def _context_menu(self):
        m = QMenu(self)
        m.addAction("Открыть", lambda: self.panel._open_file(self.entry.uid))
        m.addAction("Показать в папке", lambda: self.panel._show_in_folder(self.entry.uid))
        m.addSeparator()
        m.addAction("Пауза", lambda: self.panel._pause(self.entry.uid))
        m.addAction("Продолжить", lambda: self.panel._resume(self.entry.uid))
        m.addAction("Отмена", lambda: self.panel._cancel(self.entry.uid))
        m.addAction("Повторить", lambda: self.panel._retry(self.entry.uid))
        m.addSeparator()
        m.addAction("Удалить из списка", lambda: self.panel._remove_entry(self.entry.uid))
        m.exec_(QCursor.pos())

    def _build_subtitle(self) -> str:
        e = self.entry
        spd = e._runtime.get("speed_bps") or 0.0
        speed_txt = f"{_human_size(spd)}/s" if spd > 1 else ""
        if e.bytes_total > 0:
            eta_txt = _human_eta(e.bytes_total - e.bytes_received, spd) if spd > 1 else "—"
            frac = f"{_human_size(e.bytes_received)} из {_human_size(e.bytes_total)}"
        else:
            eta_txt = "—"
            frac = _human_size(e.bytes_received)
        return (f"<span style='color:#9bb0c5'>{e.status}</span> • "
                f"{frac} • {speed_txt} • ETA: {eta_txt} • "
                f"<span style='color:#8397ac'>{e.date}</span>")

    def update_from_entry(self):
        self.title_lbl.setText(self.entry.filename or "—")
        self.sub_lbl.setText(self._build_subtitle())
        self.progress.setValue(self.entry.progress or 0)
        self._refresh_buttons()

    def _refresh_buttons(self):
        st = self.entry.status
        downloading = st == "Загрузка"
        done = st == "Готово"
        error = st == "Ошибка"
        canceled = st == "Отменено"

        can_pause = downloading and self.panel._has_pause(self.entry.uid)
        can_resume = (downloading and self.panel._has_pause(self.entry.uid)) or error or canceled

        self.btn_pause.setEnabled(can_pause and not self.panel._is_paused(self.entry.uid))
        self.btn_resume.setEnabled(can_resume)
        self.btn_cancel.setEnabled(downloading)
        self.btn_open.setEnabled(done and os.path.exists(self.entry.path))
        self.btn_folder.setEnabled(os.path.exists(os.path.dirname(self.entry.path)) if self.entry.path else False)
        self.btn_retry.setEnabled(error or canceled)

# ---------- Панель ----------

class DownloadsPanel(QWidget):
    """
    Панель загрузок. Интеграция:
      - подключите профиль: profile.downloadRequested.connect(panel.handle_download)
      - для Повторить: установите callback self.request_download(url) если нужен кастомный.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Жүктеулер / Загрузки")
        self.setMinimumSize(640, 420)
        self.setObjectName("DownloadsPanel")

        # Внешний колбэк для повтора (может быть установлен снаружи)
        self.request_download: Optional[Callable[[str], None]] = None

        self.entries: List[DownloadEntry] = []
        self._active: Dict[str, QWebEngineDownloadItem] = {}   # uid -> item
        self._speed_cache: Dict[str, tuple] = {}               # uid -> (last_bytes, last_time, speed_bps)
        self._paused: Dict[str, bool] = {}

        self._build_ui()
        self._apply_styles()
        self._load_history()
        self._install_shortcuts()

        # Таймер обновления скорости/ETA раз в 500 мс
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._recompute_speeds)
        self._timer.start(500)

    def attach_to_default_profile(self):
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineProfile
            prof = QWebEngineProfile.defaultProfile()
            prof.downloadRequested.connect(self.handle_download)
        except Exception:
            pass


    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        header = QHBoxLayout()
        header.setSpacing(8)

        title = QLabel("Загрузки")
        title.setObjectName("hdrTitle")

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск…")
        self.search_edit.textChanged.connect(self._refilter)

        self.filter_box = QComboBox()
        self.filter_box.addItems(["Все", "Активные", "Готово", "Ошибка", "Отменено"])
        self.filter_box.currentIndexChanged.connect(self._refilter)

        btn_export = QToolButton(); btn_export.setText("Экспорт"); btn_export.clicked.connect(self._export_json)
        btn_import = QToolButton(); btn_import.setText("Импорт"); btn_import.clicked.connect(self._import_json)
        btn_clear  = QToolButton(); btn_clear.setText("Очистить"); btn_clear.clicked.connect(self._clear_all)

        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.search_edit)
        header.addWidget(self.filter_box)
        header.addWidget(btn_export)
        header.addWidget(btn_import)
        header.addWidget(btn_clear)

        # List
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("dlList")
        self.list_widget.setUniformItemSizes(False)
        self.list_widget.setSpacing(6)
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)

        root.addLayout(header)
        root.addWidget(self.list_widget)

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget { color: #e6e9ee; font: 10.5pt 'Segoe UI'; }
            #dlList { border: 1px solid #1b2734; border-radius: 10px; background: #0f141b; padding: 8px; }
            QLabel#hdrTitle { font-weight: 700; }
            QLabel#dlTitle { font-weight: 600; }
            QLabel#dlSub { color:#9aa6b9; font-size: 10.5pt; }

            QWidget#dlRow {
                background: #0f141b;
                border: 1px solid #1a2430;
                border-radius: 10px;
            }
            QToolButton, QPushButton {
                padding: 6px 10px; background:#141b24; border:1px solid #1f2732; border-radius:8px;
            }
            QToolButton:hover, QPushButton:hover { background:#17202b; border-color:#2a384a; }

            QLineEdit {
                min-width: 220px; padding: 6px 10px;
                background:#121a23; color:#e6e9ee; border:1px solid #223043; border-radius:8px;
            }
            QLineEdit:focus { border-color:#2d76c9; }
            QComboBox { padding: 4px 8px; background:#121a23; border:1px solid #223043; border-radius:8px; }
            QComboBox::drop-down { width: 20px; }
        """)

    def _install_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_edit.setFocus())
        QShortcut(QKeySequence("Delete"), self, self._delete_selected)
        QShortcut(QKeySequence("Ctrl+E"), self, self._export_json)
        QShortcut(QKeySequence("Ctrl+I"), self, self._import_json)

    # ---------- Работа со списком ----------
    def _make_item_widget(self, entry: DownloadEntry) -> _RowWidget:
        w = _RowWidget(self, entry)
        it = QListWidgetItem()
        it.setSizeHint(QSize(10, 86))
        self.list_widget.addItem(it)
        self.list_widget.setItemWidget(it, w)
        return w

    def _refresh_list(self):
        self.list_widget.setUpdatesEnabled(False)
        self.list_widget.clear()
        needle = (self.search_edit.text() or "").lower()
        status_filter = self.filter_box.currentText()

        for e in self.entries:
            if needle and not (needle in (e.filename or "").lower() or needle in (e.url or "").lower()):
                continue
            if status_filter != "Все" and e.status != status_filter and not (status_filter == "Активные" and e.status == "Загрузка"):
                continue
            self._make_item_widget(e)

        self.list_widget.setUpdatesEnabled(True)

    def _refilter(self):
        self._refresh_list()

    # ---------- Публичный API для профиля ----------
    def handle_download(self, download_item: QWebEngineDownloadItem):
        """Подключи это к profile.downloadRequested."""
        suggested = download_item.path() or os.path.basename(download_item.url().path())
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", suggested)
        if not path:
            download_item.cancel()
            return

        download_item.setPath(path)
        download_item.accept()

        uid = f"{int(time.time()*1000)}_{len(self.entries)}"
        entry = DownloadEntry(
            uid=uid,
            url=download_item.url().toString(),
            filename=os.path.basename(path),
            path=path,
            status="Загрузка",
            date=time.strftime("%Y-%m-%d %H:%M:%S"),
            progress=0,
            bytes_received=0,
            bytes_total=int(download_item.totalBytes() or 0),
            mime_type=getattr(download_item, "mimeType", lambda: "")() if hasattr(download_item, "mimeType") else "",
        )
        self.entries.append(entry)
        self._active[uid] = download_item
        self._speed_cache[uid] = (0, time.time(), 0.0)

        # Сигналы
        download_item.downloadProgress.connect(lambda rec, tot, u=uid: self._on_progress(u, rec, tot))
        download_item.finished.connect(lambda u=uid: self._on_finished(u))

        self._save_history()
        self._refilter()

    # ---------- Сигналы загрузки ----------
    def _on_progress(self, uid: str, received: int, total: int):
        e = self._find_entry(uid)
        if not e:
            return
        e.bytes_received = int(received)
        e.bytes_total = int(total or e.bytes_total)
        e.progress = int((received * 100 / total) if total > 0 else 0)
        e.status = "Загрузка"

        # скорость
        last = self._speed_cache.get(uid, (0, time.time(), 0.0))
        last_b, last_t, last_speed = last
        now = time.time()
        dt = now - last_t
        speed = ((received - last_b) / dt) if dt > 0.2 else last_speed
        self._speed_cache[uid] = (received, now, speed)
        e._runtime["speed_bps"] = speed

        self._update_row(uid)

    def _on_finished(self, uid: str):
        e = self._find_entry(uid)
        item = self._active.get(uid)
        if e:
            state = item.state() if item else None
            if state == QWebEngineDownloadItem.DownloadCompleted:
                e.status = "Готово"
                e.progress = 100
            elif state == QWebEngineDownloadItem.DownloadCancelled:
                e.status = "Отменено"
            else:
                e.status = "Ошибка"
                e.error_string = getattr(item, "interruptReasonString", lambda: "")() if hasattr(item, "interruptReasonString") else ""
        self._active.pop(uid, None)
        self._save_history()
        self._update_row(uid)

    def _recompute_speeds(self):
        # Периодически обновляем сабтайтлы активных строк
        for uid in list(self._active.keys()):
            self._update_row(uid)

    # ---------- Действия ----------
    def _find_entry(self, uid: str) -> Optional[DownloadEntry]:
        for e in self.entries:
            if e.uid == uid:
                return e
        return None

    def _row_widget_for(self, uid: str) -> Optional[_RowWidget]:
        for i in range(self.list_widget.count()):
            w = self.list_widget.itemWidget(self.list_widget.item(i))
            if isinstance(w, _RowWidget) and w.entry.uid == uid:
                return w
        return None

    def _update_row(self, uid: str):
        e = self._find_entry(uid)
        w = self._row_widget_for(uid)
        if e and w:
            w.update_from_entry()

    # --- пауза/резюм/отмена (если поддерживается движком) ---
    def _has_pause(self, uid: str) -> bool:
        item = self._active.get(uid)
        return hasattr(item, "pause") and hasattr(item, "resume")

    def _is_paused(self, uid: str) -> bool:
        return self._paused.get(uid, False)

    def _pause(self, uid: str):
        item = self._active.get(uid)
        if item and hasattr(item, "pause"):
            try:
                item.pause()
                self._paused[uid] = True
            except Exception:
                pass
        self._update_row(uid)

    def _resume(self, uid: str):
        item = self._active.get(uid)
        if item and hasattr(item, "resume"):
            try:
                item.resume()
                self._paused[uid] = False
            except Exception:
                pass
        else:
            # Если это уже завершившийся элемент — даём «повторить»
            self._retry(uid)
        self._update_row(uid)

    def _cancel(self, uid: str):
        item = self._active.get(uid)
        if item:
            try:
                item.cancel()
            except Exception:
                pass

    def _open_file(self, uid: str):
        e = self._find_entry(uid)
        if not e or not e.path:
            return
        if os.path.exists(e.path):
            try:
                os.startfile(e.path)
            except Exception as ex:
                QMessageBox.warning(self, "Ошибка", f"Не удалось открыть файл:\n{ex}")
        else:
            QMessageBox.information(self, "Файл не найден", "Файл был удалён или перемещён.")

    def _show_in_folder(self, uid: str):
        e = self._find_entry(uid)
        if not e or not e.path:
            return
        folder = os.path.dirname(e.path)
        if os.path.isdir(folder):
            try:
                os.startfile(folder)
            except Exception as ex:
                QMessageBox.warning(self, "Ошибка", f"Не удалось открыть папку:\n{ex}")

    def _retry(self, uid: str):
        e = self._find_entry(uid)
        if not e: return
        if callable(self.request_download):
            self.request_download(e.url)
        else:
            # по умолчанию просто предложим сохранить снова
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить файл", e.filename or os.path.basename(e.path))
            if path:
                # эмулировать новое скачивание должен внешний профиль; тут только сигнализируем пользователю
                QMessageBox.information(self, "Повтор", "Повтор загрузки должен инициироваться браузером.\nПодключи callback request_download(url).")

    def _remove_entry(self, uid: str):
        self.entries = [x for x in self.entries if x.uid != uid]
        self._save_history()
        self._refilter()

    def _delete_selected(self):
        # Удалить выбранные строки из списка (истории UI)
        to_remove = []
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            w = self.list_widget.itemWidget(it)
            if self.list_widget.isItemSelected(it) and isinstance(w, _RowWidget):
                to_remove.append(w.entry.uid)
        if not to_remove:
            return
        self.entries = [e for e in self.entries if e.uid not in to_remove]
        self._save_history()
        self._refilter()

    # ---------- История ----------
    def _save_history(self):
        try:
            with open(DOWNLOADS_JSON, "w", encoding="utf-8") as f:
                json.dump([e.to_json() for e in self.entries], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[downloads_ui] Не удалось сохранить историю: {e}")

    def _load_history(self):
        if os.path.exists(DOWNLOADS_JSON):
            try:
                with open(DOWNLOADS_JSON, "r", encoding="utf-8") as f:
                    raw = json.load(f) or []
                self.entries = [DownloadEntry.from_json(d) for d in raw]
                self._refilter()
            except Exception as e:
                print(f"[downloads_ui] Ошибка загрузки истории: {e}")

    def _export_json(self):
        """Экспорт истории в JSON-файл по выбору пользователя."""
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт истории загрузок", "downloads_history.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([e.to_json() for e in self.entries], f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Экспорт", "История успешно экспортирована.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка экспорта", str(e))

    def _import_json(self):
        """Импорт истории из JSON и слияние с текущей."""
        path, _ = QFileDialog.getOpenFileName(self, "Импорт истории загрузок", "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f) or []
            imported = [DownloadEntry.from_json(d) for d in raw]
            # простое слияние по uid (если uid пустой — добавим новый со временем)
            existing_uids = {e.uid for e in self.entries}
            for e in imported:
                if not e.uid:
                    e.uid = f"imp_{int(time.time()*1000)}_{len(self.entries)}"
                if e.uid not in existing_uids:
                    self.entries.append(e)
            self._save_history()
            self._refilter()
            QMessageBox.information(self, "Импорт", "История успешно импортирована.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка импорта", str(e))

    def _clear_all(self):
        if QMessageBox.question(self, "Очистить?", "Удалить всю историю загрузок?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.entries.clear()
            self._save_history()
            self._refilter()

    # ---------- Вспомогательные публичные методы ----------
    def show_downloads(self):
        """Совместимо с вызовом из навбара."""
        self._refilter()
        self.show()
        self.raise_()
        self.activateWindow()
