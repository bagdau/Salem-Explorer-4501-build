# -*- coding: utf-8 -*-
"""
BookmarksBar — компактная панель закладок с корректной интеграцией в ГЛОБАЛЬНЫЙ QSS.

Ключевые изменения vs прежней версии:
- Добавлен публичный метод set_global_stylesheet(css: str) — переводит панель в режим
  «использовать глобальный QSS», очищая локальный styleSheet(), чтобы начали работать
  селекторы вида `QToolBar#bookmarks_bar ...` из app.setStyleSheet(css).
- Локальный QSS теперь применяется только как Fallback ДО того, как хост передаст глобальный QSS.
- Сохранена совместимость API, поведение и UX (overflow, «+» меню, контекстное меню, favicons).

Интеграция на стороне хоста:
- После создания панели назначьте objectName (уже назначен здесь) и вызовите
  bookmarks_bar.set_global_stylesheet(css) в вашей apply_global_theme(...), ПОСЛЕ app.setStyleSheet(css).
"""

import os, sys, json, urllib.parse, urllib.request
from PyQt5.QtCore import Qt, QSize, QTimer, QStandardPaths, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QToolBar, QAction, QInputDialog, QMenu, QToolButton, QWidgetAction,
    QFileDialog
)


class BookmarksBar(QToolBar):
    """
    Компактная панель закладок с нормальным UX:
      • Оверфлоу («»») при нехватке места
      • Кнопка «+» с меню (добавить, из текущей вкладки, импорт/экспорт)
      • Контекстное меню на элементах (переименовать/удалить/сдвинуть)
      • Кэш фавиконок
    Общение с хостом — через сигналы:
      openRequested(url:str, title:str)
      openInNewRequested(url:str, title:str)
    """

    openRequested = pyqtSignal(str, str)
    openInNewRequested = pyqtSignal(str, str)

    def __init__(
        self, parent=None, *,
        icon_size=QSize(18, 18),
        asset_resolver=None,
        data_dir=None,
        current_view_resolver=None,  # callable -> returns QWebEngineView (или совместимый)
    ):
        super().__init__("Закладки", parent)
        # ИМЯ ВАЖНО: глобальные QSS-правила вида QToolBar#bookmarks_bar ...
        self.setObjectName("bookmarks_bar")
        self.setIconSize(icon_size)
        self.setMovable(False)
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        # Кнопки с текстом рядом с иконкой, как в браузерах
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        # внешние зависимости
        self._asset = asset_resolver or (lambda p: p)
        self._current_view = current_view_resolver  # функция, возвращающая активный webview

        # директории данных
        base = data_dir or QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".salem")
        os.makedirs(base, exist_ok=True)
        self._base_dir = base
        self._fav_dir = os.path.join(self._base_dir, "favicons")
        os.makedirs(self._fav_dir, exist_ok=True)
        self._json_path = os.path.join(self._base_dir, "bookmarks.json")

        # модель
        self._list = []  # [{title:str, url:str}]
        self._bm_actions = []  # QAction на «кнопки» закладок
        self._overflow_action = None  # QWidgetAction с QToolButton » (меню переполнения)
        self._plus_action = None      # QWidgetAction с QToolButton + (меню)

        # режимы стилей
        self._use_global_qss = False  # пока False: применяем локальный Fallback до инициализации темы
        self._last_global_css = None  # для отладки/диагностики (хранится, но не обязателен)

        self.load()
        self._apply_qss()  # локальный Fallback (будет отключён после set_global_stylesheet)
        self.refresh()

    # ----------------- Публичный API -----------------
    def add(self, url: str, title: str = None):
        if not url:
            return
        if not title:
            title = url
        if any(b.get("url") == url for b in self._list):
            return
        self._list.append({"title": title, "url": url})
        self.save(); self.refresh()

    def add_from_view(self):
        view = None
        if callable(self._current_view):
            try:
                view = self._current_view()
            except Exception:
                view = None
        if not view:
            return
        try:
            url = view.url().toString()
            title = getattr(view, "title", lambda: url)()
        except Exception:
            return
        self.add(url, title)

    def toggle(self):
        self.setVisible(not self.isVisible())

    def set_global_stylesheet(self, css: str):
        """Переводит панель в режим использования ГЛОБАЛЬНОГО QSS.
        Важно: сам css строкой передаётся для совместимости, но намеренно НЕ ставится локально,
        чтобы приоритет был у app.setStyleSheet(css). Мы просто очищаем локальный стиль.
        """
        self._use_global_qss = True
        self._last_global_css = css
        # Сбрасываем локальный стиль. Теперь начнут применяться глобальные селекторы
        # вида QToolBar#bookmarks_bar ...
        self.setStyleSheet("")
        self._repolish()
        # После смены стиля ширины кнопок могли измениться → пересоберём Overflow
        QTimer.singleShot(0, self._layout_overflow)

    # ----------------- Рендер/Данные -----------------
    def refresh(self):
        self.clear()
        self._bm_actions.clear()

        # Рисуем закладки
        for idx, b in enumerate(self._list):
            title = b.get("title") or b.get("url")
            url = b.get("url")
            icon = self._favicon(url, self.iconSize().width())
            act = QAction(icon, title, self)
            act.setData(idx)
            act.setToolTip(url)
            act.triggered.connect(lambda _, i=idx: self._open(i))
            self.addAction(act)
            self._bm_actions.append(act)

        # Оверфлоу » (DropDown с переполнением)
        self._add_overflow_button()

        # Плюс-кнопка с меню
        self._add_plus_button()

        # После построения — переразложить с учётом доступной ширины
        QTimer.singleShot(0, self._layout_overflow)

    # кнопка «»» (overflow)
    def _add_overflow_button(self):
        btn = QToolButton(self)
        btn.setObjectName("bm_overflow")
        btn.setText("»")
        btn.setToolTip("Показать скрытые закладки")
        btn.setPopupMode(QToolButton.InstantPopup)
        btn.setMenu(QMenu(btn))

        act = QWidgetAction(self)
        act.setDefaultWidget(btn)
        self.addAction(act)
        self._overflow_action = act

    # кнопка «+» с меню
    def _add_plus_button(self):
        btn = QToolButton(self)
        btn.setObjectName("bm_plus")
        btn.setIcon(self._safe_icon("img/icons/plus.svg"))
        btn.setToolTip("Меню закладок")
        btn.setPopupMode(QToolButton.InstantPopup)

        m = QMenu(btn)
        m.addAction("Добавить закладку…", self._prompt_add)
        m.addAction("Добавить текущую вкладку", self.add_from_view)
        m.addSeparator()
        m.addAction("Импорт…", self._import_json)
        m.addAction("Экспорт…", self._export_json)
        m.addSeparator()
        m.addAction("Скрыть панель", self.toggle)
        btn.setMenu(m)

        act = QWidgetAction(self)
        act.setDefaultWidget(btn)
        self.addAction(act)
        self._plus_action = act

    # Динамическое скрытие и переполнение
    def _layout_overflow(self):
        if not self._overflow_action or not self._plus_action:
            return

        overflow_btn = self._overflow_btn()
        plus_btn = self._plus_btn()
        if not overflow_btn or not plus_btn:
            return

        # ширина, доступная под закладки (минус «плюс» и «оверфлоу» и внутренние паддинги)
        reserved = plus_btn.sizeHint().width() + overflow_btn.sizeHint().width() + 16
        avail = max(0, self.width() - reserved)

        hidden = []
        used = 0
        # Сначала покажем все
        for act in self._bm_actions:
            w = self.widgetForAction(act)
            if not w:
                continue
            ww = w.sizeHint().width()
            # если влезает — показываем, иначе скрываем
            if used + ww <= avail:
                act.setVisible(True)
                used += ww
            else:
                act.setVisible(False)
                hidden.append(act)

        # Обновим меню переполнения
        menu = overflow_btn.menu()
        menu.clear()
        if not hidden:
            overflow_btn.setEnabled(False)
            overflow_btn.setToolTip("Все закладки видимы")
        else:
            overflow_btn.setEnabled(True)
            overflow_btn.setToolTip("Скрытые закладки")
            for act in hidden:
                idx = int(act.data()) if act.data() is not None else None
                title = act.text()
                icon = act.icon()
                a = QAction(icon, title, menu)
                # Открыть в этой же вкладке
                a.triggered.connect(lambda _, i=idx: self._open(i))
                menu.addAction(a)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._layout_overflow)

    def load(self):
        if os.path.isfile(self._json_path):
            try:
                with open(self._json_path, "r", encoding="utf-8") as f:
                    self._list = json.load(f)
            except Exception:
                self._list = []
        else:
            self._list = [
                {"title": "Salem Home", "url": "http://127.0.0.1:5000/"},
                {"title": "Media",      "url": "http://127.0.0.1:7000/media"},
            ]
            self.save()

    def save(self):
        try:
            with open(self._json_path, "w", encoding="utf-8") as f:
                json.dump(self._list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ----------------- Контекстное меню -----------------
    def _on_context_menu(self, pos):
        act = self.actionAt(pos)
        m = QMenu(self)

        # Правый клик по конкретной закладке
        if act and act.data() is not None:
            idx = int(act.data())
            m.addAction("Открыть",                 lambda i=idx: self._open(i))
            m.addAction("Открыть в новой вкладке", lambda i=idx: self._open_new(i))
            m.addSeparator()
            m.addAction("Переименовать…",          lambda i=idx: self._rename(i))
            m.addAction("Изменить URL…",           lambda i=idx: self._change_url(i))
            m.addAction("Удалить",                 lambda i=idx: self._remove(i))
            m.addSeparator()
            m.addAction("Сдвинуть влево",          lambda i=idx: self._move(i, -1))
            m.addAction("Сдвинуть вправо",         lambda i=idx: self._move(i, +1))
        else:
            # Пустая зона/оверфлоу/плюс
            m.addAction("Добавить закладку…", self._prompt_add)
            m.addAction("Добавить текущую вкладку", self.add_from_view)
            m.addSeparator()
            m.addAction("Импорт…", self._import_json)
            m.addAction("Экспорт…", self._export_json)
            m.addSeparator()
            m.addAction("Скрыть панель", self.toggle)
        m.exec_(self.mapToGlobal(pos))

    # ----------------- Вспомогательное -----------------
    def _open(self, idx: int):
        try:
            b = self._list[idx]
            self.openRequested.emit(b["url"], b.get("title") or b["url"])
        except Exception:
            pass

    def _open_new(self, idx: int):
        try:
            b = self._list[idx]
            self.openInNewRequested.emit(b["url"], b.get("title") or b["url"])
        except Exception:
            pass

    def _rename(self, idx: int):
        b = self._list[idx]
        title, ok = QInputDialog.getText(self, "Переименовать", "Название:", text=b.get("title") or b.get("url"))
        if not ok: return
        b["title"] = (title or b.get("url")).strip()
        self.save(); self.refresh()

    def _change_url(self, idx: int):
        b = self._list[idx]
        url, ok = QInputDialog.getText(self, "Изменить URL", "URL:", text=b.get("url"))
        if not ok: return
        b["url"] = (url or b.get("url")).strip()
        self.save(); self.refresh()

    def _remove(self, idx: int):
        del self._list[idx]
        self.save(); self.refresh()

    def _move(self, idx: int, delta: int):
        j = idx + delta
        if 0 <= j < len(self._list):
            self._list[idx], self._list[j] = self._list[j], self._list[idx]
            self.save(); self.refresh()

    def _prompt_add(self):
        url, ok = QInputDialog.getText(self, "Новая закладка", "URL:")
        if not ok or not url.strip(): return
        title, ok2 = QInputDialog.getText(self, "Новая закладка", "Название:", text=url)
        if not ok2: return
        self.add(url.strip(), (title or url).strip())

    def _import_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт закладок", "", "JSON (*.json)")
        if not path: return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                # простая схема: мердж по url, новые — в конец
                known = {b.get("url") for b in self._list}
                for item in data:
                    if isinstance(item, dict) and item.get("url") and item.get("url") not in known:
                        self._list.append({"title": item.get("title") or item["url"], "url": item["url"]})
                self.save(); self.refresh()
        except Exception:
            pass

    def _export_json(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт закладок", "bookmarks.json", "JSON (*.json)")
        if not path: return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._list, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _favicon(self, url: str, size: int) -> QIcon:
        try:
            domain = urllib.parse.urlparse(url).netloc or url
            name = domain.replace(":", "_") + f"_{size}.png"
            path = os.path.join(self._fav_dir, name)
            if os.path.isfile(path):
                return QIcon(path)
            api = f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(domain)}&sz={size}"
            with urllib.request.urlopen(api, timeout=5) as r:
                data = r.read()
            with open(path, "wb") as f:
                f.write(data)
            return QIcon(path)
        except Exception:
            return self._safe_icon("img/icons/bookmark.svg")

    def _safe_icon(self, rel):
        try:
            p = self._asset(rel)
            return QIcon(p)
        except Exception:
            pass
        base = getattr(sys, "_MEIPASS", os.path.dirname(__file__))
        p2 = os.path.join(base, rel.replace("/", os.sep))
        return QIcon(p2)

    # helpers
    def _overflow_btn(self) -> QToolButton:
        if not self._overflow_action: return None
        return self._overflow_action.defaultWidget()

    def _plus_btn(self) -> QToolButton:
        if not self._plus_action: return None
        return self._plus_action.defaultWidget()

    # ----------------- Стиль (Fallback локальный) -----------------
    def _apply_qss(self):
        """Локальный стиль только как Fallback до прихода глобального QSS.
        Как только хост вызовет set_global_stylesheet(...), локальный стиль будет очищен.
        """
        if self._use_global_qss:
            # Используем ГЛОБАЛЬНЫЙ QSS (app.setStyleSheet). Локальный стиль выключен.
            self.setStyleSheet("")
            return

        # Fallback-оформление (тёмная тема по умолчанию)
        self.setStyleSheet(
            """
            QToolBar#bookmarks_bar {
                background: rgba(15,17,23,0.92);
                border: 1px solid #1e293b;
                border-radius: 10px;
                padding: 4px;
            }
            QToolBar#bookmarks_bar::separator { width: 0px; height: 0px; }

            /* обычные кнопки-закладки */
            QToolBar#bookmarks_bar QToolButton {
                min-height: 30px;
                padding: 4px 10px;
                border-radius: 8px;
                border: 1px solid #223046;
                background: #111827;
                color: #e6edf3;
            }
            QToolBar#bookmarks_bar QToolButton:hover {
                border-color: #22d3ee;
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #172131, stop:1 #0f1824);
                color: #dffaff;
            }
            QToolBar#bookmarks_bar QToolButton:pressed { background: #1b2434; }

            /* плюс и оверфлоу — пилюли */
            QToolBar#bookmarks_bar QToolButton#bm_plus,
            QToolBar#bookmarks_bar QToolButton#bm_overflow {
                min-width: 34px;
                min-height: 30px;
                padding: 0 10px;
                border-radius: 9px;
                border: 1px solid #2b3a4e;
                background: #1a2332;
                color: #d4dbe5;
            }
            QToolBar#bookmarks_bar QToolButton#bm_plus:hover,
            QToolBar#bookmarks_bar QToolButton#bm_overflow:hover {
                background: #223046;
                border-color: #22d3ee;
                color: #22d3ee;
            }

            /* меню */
            QMenu { background: #0f141b; color: #e6edf3; border: 1px solid #223046; }
            QMenu::item { padding: 6px 12px; }
            QMenu::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #22d3ee, stop:1 #6E9CFF);
                color: #0b0e14;
            }
            """
        )

    def _repolish(self):
        s = self.style()
        s.unpolish(self)
        s.polish(self)
        self.update()
