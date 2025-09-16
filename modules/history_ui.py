# -*- coding: utf-8 -*-
"""
modules/history_ui.py — вкладочная версия панели истории для Salem Explorer (PyQt5)

Экспортирует: HistoryPanel (QWidget)
— Работает строго как содержимое вкладки (никаких отдельных окон)
— Поиск по истории, удаление записей, очистка, импорт/экспорт
— Метод add_entry(url, title="") для добавления записей из браузера
— Данные сохраняются в пользовательском каталоге (QStandardPaths.AppDataLocation)
"""
from __future__ import annotations

import os
import json
from typing import List, Dict

from PyQt5.QtCore import Qt, QStandardPaths
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QMessageBox, QFileDialog
)

__all__ = ["HistoryPanel"]


def _history_path() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or os.getcwd()
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "salem_history.json")


class HistoryPanel(QWidget):
    """Панель истории как вкладка браузера.

    open_callback: callable(url) — если задан, по кнопке «Открыть» навигируем в браузере
    """
    def __init__(self, open_callback=None, parent=None):
        super().__init__(parent)
        self.open_callback = open_callback
        self._store_file = _history_path()
        self._history: List[Dict[str, str]] = []
        self._filtered: List[Dict[str, str]] = []
        self._build_ui()
        self._load()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        self.setObjectName("HistoryPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Поиск
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Поиск по истории…")
        self.search.textChanged.connect(self._refilter)
        root.addWidget(self.search)

        # Список
        self.listw = QListWidget(self)
        root.addWidget(self.listw, 1)
        # Пробиваем цвет текста непосредственно на viewport списка (на случай агрессивного глобального QSS)
        self.listw.viewport().setStyleSheet("color:#e6e8ee;")

        # Кнопки
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_export = QPushButton("⬆ Экспорт", self)
        self.btn_import = QPushButton("⬇ Импорт", self)
        self.btn_clear  = QPushButton("🧹 Очистить всё", self)
        bar.addWidget(self.btn_export)
        bar.addWidget(self.btn_import)
        bar.addStretch(1)
        bar.addWidget(self.btn_clear)
        root.addLayout(bar)

        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        self.btn_clear.clicked.connect(self._clear_all)

        # Аккуратная тёмная палитра: делаем placeholder читаемым (с фолбэком для старых Qt)
        pal = self.search.palette()
        try:
            role = QPalette.PlaceholderText  # Qt >= 5.12
        except AttributeError:
            role = QPalette.Text
        pal.setColor(role, QColor("#8aa0b6"))
        self.search.setPalette(pal)

        # Стиль (темный, без неона) + ЯВНЫЕ цвета текста для всех потомков
        self.setStyleSheet("""
        /* 1) Весь текст внутри панели — читаемый */
        /* === Базовый читаемый текст === */
        QWidget { color: #e6e8ee; }              /* тёмная тема */
         /* для светлой темы можно поставить #0f172a */
        
        /* === Списки / таблицы / дерево (история обычно тут) === */
        QAbstractItemView {
            color: #e6e8ee;
            background: #121826;                 /* фон таблицы/списка */
            selection-background-color: #1f2a44; /* фон выделения */
            selection-color: #ffffff;            /* текст выделенной строки */
        }
        QAbstractItemView::item { color: #e6e8ee; }
        QAbstractItemView::item:selected { color: #ffffff; }
        
        /* === Текстовые поля === */
        QLineEdit, QTextEdit, QPlainTextEdit {
            color: #e6e8ee;
            background: #0f1117;
            selection-background-color: #1f2a44;
            selection-color: #ffffff;
        }
        
        /* === Заголовки/ярлыки/кнопки === */
        QLabel, QGroupBox, QCheckBox, QRadioButton, QPushButton, QToolButton { color: #e6e8ee; }
        
        /* === Отключённые (чтобы не исчезали) === */
        *:disabled { color: rgba(230,232,238,.45); }
        
        /* === На всякий случай для ссылок в rich-text === */
        QTextBrowser, QLabel[textFormat="RichText"] { color: #8ab4f8; }

        """)

        # Страховочная палитра на всю панель (некоторые стили читают именно палитру)
        pal_all = self.palette()
        pal_all.setColor(QPalette.WindowText, QColor("#e6e8ee"))
        pal_all.setColor(QPalette.Text,       QColor("#e6e8ee"))
        pal_all.setColor(QPalette.Highlight,  QColor("#1f2a44"))
        pal_all.setColor(QPalette.HighlightedText, QColor("#ffffff"))
        self.setPalette(pal_all)

    # ---------------- Data I/O ----------------
    def _load(self) -> None:
        try:
            if os.path.isfile(self._store_file):
                with open(self._store_file, "r", encoding="utf-8") as f:
                    self._history = json.load(f) or []
        except Exception:
            self._history = []
        self._refilter()

    def _save(self) -> None:
        try:
            with open(self._store_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------------- Public API ----------------
    def add_entry(self, url: str, title: str = "") -> None:
        if not url:
            return
        # простая дедупликация последнего URL
        if self._history and self._history[-1].get("url") == url:
            return
        self._history.append({"url": url, "title": title or url})
        self._save()
        self._refilter()

    def set_history(self, rows: List[Dict[str, str]]) -> None:
        self._history = list(rows or [])
        self._save()
        self._refilter()

    # ---------------- Filtering & render ----------------
    def _refilter(self) -> None:
        q = (self.search.text() or "").strip().lower()
        if not q:
            self._filtered = list(self._history)
        else:
            self._filtered = [
                h for h in self._history
                if q in (h.get("url", "").lower() + " " + h.get("title", "").lower())
            ]
        self._render_list()

    def _render_list(self) -> None:
        self.listw.clear()
        # последние сверху
        for idx, row in enumerate(reversed(self._filtered)):
            url = row.get("url", "")
            title = row.get("title", url)

            wrap = QWidget()
            lay = QHBoxLayout(wrap)
            lay.setContentsMargins(10, 8, 10, 8)
            lay.setSpacing(8)

            lbl = QLabel(
                f"<b>{self._safe_html(title)}</b>"
                f"<br><span style='color:#8aa0b6;font-size:11px'>{self._safe_html(url)}</span>"
            )
            # прибиваем формат/интерактивность/цвет прямо на лейбле — сильнее любого внешнего QSS
            lbl.setTextFormat(Qt.RichText)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lbl.setStyleSheet("color:#e6e8ee;")

            btn_open = QPushButton("Открыть")
            btn_del  = QPushButton("Удалить")
            btn_open.setMaximumWidth(84)
            btn_del.setMaximumWidth(84)

            lay.addWidget(lbl, 1)
            lay.addWidget(btn_open)
            lay.addWidget(btn_del)

            def _go(u=url):
                if callable(self.open_callback):
                    self.open_callback(u)

            # Удаляем корректно с учётом фильтрации/дубликатов: ищем реальный индекс в self._history с конца
            def _remove(u=url, t=title):
                try:
                    for j in range(len(self._history) - 1, -1, -1):
                        r = self._history[j]
                        if r.get("url") == u and r.get("title", u) == t:
                            self._history.pop(j)
                            break
                    self._save()
                    self._refilter()
                except Exception:
                    pass

            btn_open.clicked.connect(_go)
            btn_del.clicked.connect(_remove)

            it = QListWidgetItem()
            it.setSizeHint(wrap.sizeHint())
            self.listw.addItem(it)
            self.listw.setItemWidget(it, wrap)

    # ---------------- Actions ----------------
    def _clear_all(self) -> None:
        if QMessageBox.question(
            self, "Очистка", "Очистить всю историю?", QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        self._history.clear()
        self._save()
        self._refilter()

    def _export(self) -> None:
        fname, _ = QFileDialog.getSaveFileName(self, "Экспорт истории", "history.json", "JSON (*.json)")
        if not fname:
            return
        try:
            with open(fname, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Экспорт", "История экспортирована!")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка: {e}")

    def _import(self) -> None:
        fname, _ = QFileDialog.getOpenFileName(self, "Импорт истории", "", "JSON (*.json)")
        if not fname:
            return
        try:
            with open(fname, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._history.extend(data)
                self._save()
                self._refilter()
                QMessageBox.information(self, "Импорт", "Импорт завершён!")
            else:
                QMessageBox.warning(self, "Ошибка", "Файл не содержит историю.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Ошибка: {e}")

    # ---------------- Utils ----------------
    @staticmethod
    def _safe_html(s: str) -> str:
        return (
            (s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
