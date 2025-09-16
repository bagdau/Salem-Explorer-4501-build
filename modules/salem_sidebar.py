# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Salem Sidebar (GX-style), чистый и современный, без кислотных неонов.
- Меню (страница 0) — вертикальная колонка иконок в аккуратной «карточке».
- Настройки (страница 1) — GX-свитчи, пресеты акцента, шрифты, приватность.
- SVG-иконки работают в сборке (QtSvg импортирован).
- Тема (тёмная/светлая) наследуется от контейнера вкладки.
"""

import os
from typing import Optional, Sequence, Tuple, Union, Protocol, Dict, TYPE_CHECKING

from PyQt5.QtCore import (
    Qt, QSize, QRect, QPropertyAnimation, QEasingCurve, pyqtSignal,
    QSettings, QEvent, pyqtProperty
)
from PyQt5.QtGui import QIcon, QPainter, QColor, QPen, QPixmap, QFont
from PyQt5.QtWidgets import (
    QFrame, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QLineEdit, QFileDialog, QCheckBox, QSpacerItem, QSizePolicy,
    QToolButton, QScrollArea, QStackedLayout, QAbstractButton, QColorDialog,
    QListView, QCompleter, QGridLayout
)
from PyQt5 import QtSvg  # гарантирует SVG в PyInstaller

# ──────────────────────────────────────────────────────────────────────
if TYPE_CHECKING:
    from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineSettings
else:
    try:
        from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineSettings  # type: ignore
    except Exception:  # безопасные заглушки
        class QWebEngineProfile:  # type: ignore
            def clearHttpCache(self): pass
            def cookieStore(self): return type("S", (), {"deleteAllCookies": lambda *_: None})()
            def clearAllVisitedLinks(self): pass
        class QWebEngineSettings:  # type: ignore
            PlaybackRequiresUserGesture = 0
            @staticmethod
            def globalSettings(): return QWebEngineSettings()
            def setAttribute(self, *_): pass

# ──────────────────────────────────────────────────────────────────────
class PathResolver(Protocol):
    def __call__(self, path: str) -> str: ...

class NoArgVoid(Protocol):
    def __call__(self) -> None: ...

ORG = "SalemCorp"
APP = "SalemExplorer"

# ──────────────────────────────────────────────────────────────────────
#   GX-переключатель (квадратный, с анимацией)
# ──────────────────────────────────────────────────────────────────────
class GxSwitch(QAbstractButton):
    """
    Квадратный GX-тумблер с реальной анимацией:
    - анимируется свойство value (0..1)
    - порядок: сначала анимируем, потом меняем checked
    - трек окрашивается через интерполяцию цвета (серый → акцент)
    """
    def __init__(self, checked=False, accent="#22d3ee", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        super().setChecked(bool(checked))
        self._v: float = 1.0 if checked else 0.0
        self._accent = QColor(accent)

        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumSize(38, 22)

    # ---- свойство value (0..1) ----
    def sizeHint(self): return QSize(38, 22)
    def getValue(self) -> float: return float(self._v)
    def setValue(self, v: float) -> None:
        self._v = 0.0 if v < 0 else 1.0 if v > 1 else float(v)
        self.update()
    value = pyqtProperty(float, getValue, setValue)

    # ---- смена состояния с анимацией ----
    def _start_anim(self, target_checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._v)
        self._anim.setEndValue(1.0 if target_checked else 0.0)
        self._anim.start()

    def setChecked(self, ch: bool) -> None:
        if ch == self.isChecked():
            return
        self._start_anim(bool(ch))
        super().setChecked(bool(ch))

    def nextCheckState(self) -> None:
        target = not self.isChecked()
        self._start_anim(target)
        super().setChecked(target)

    # ---- рисование ----
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)

        dark = self.palette().window().color().lightness() < 128
        base   = QColor("#1f2937" if dark else "#d1d5db")  # серый трек
        accent = self._accent

        # интерполяция цвета трека по self._v
        col = QColor(
            int(base.red()   + (accent.red()   - base.red())   * self._v),
            int(base.green() + (accent.green() - base.green()) * self._v),
            int(base.blue()  + (accent.blue()  - base.blue())  * self._v),
        )

        # трек
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, 5, 5)

        # ручка (квадратная)
        sz = r.height() - 6
        x0 = r.left() + 3
        x1 = r.right() - 3 - sz
        x  = int(x0 + (x1 - x0) * self._v)
        knob = QRect(x, r.top() + 3, sz, sz)
        p.setBrush(QColor("#0b0f14" if dark else "#ffffff"))
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.drawRoundedRect(knob, 4, 4)
        p.end()

    # обновление акцент-цвета постфактум (при смене темы)
    def setAccent(self, color: Union[str, QColor]) -> None:
        self._accent = QColor(color)
        self.update()

# ──────────────────────────────────────────────────────────────────────
#   Свотч пресета темы/акцента (используем в настройках)
# ──────────────────────────────────────────────────────────────────────
class ThemeSwatch(QPushButton):
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(title, parent)
        self.setCheckable(True)
        self._color = color
        self.setMinimumHeight(54)
        self.setCursor(Qt.PointingHandCursor)

    @property
    def color(self) -> str:
        return self._color

# ──────────────────────────────────────────────────────────────────────
class SettingsSidebar(QFrame):
    """
    Минималистичная правая панель «Меню / Настройки».
    Живёт внутри контейнера активной вкладки (anchor), без блюра и оверлея.
    """
    settingsChanged = pyqtSignal(dict)   # наружу: акцент/флаги/шрифт и т.д.
    closed = pyqtSignal()

    def __init__(self, anchor: Optional[QWidget], width: int = 500, asset_resolver: Optional[PathResolver] = None):
        super().__init__(anchor or None)
        self.setObjectName("SettingsSidebar")
        self._anchor: Optional[QWidget] = anchor
        self._asset = asset_resolver


        base_w = (anchor.width() if anchor else width)
        # Доля 28% от контейнера, но в диапазоне [470..540] px
        self._panel_width = max(470, min(540, int(base_w * 0.28)))

        self._profile: Optional[QWebEngineProfile] = None
        self._anim: Optional[QPropertyAnimation] = None
        self._accent = QSettings(ORG, APP).value("accent_color", "#22d3ee")
        self._font = QSettings(ORG, APP).value("ui_font", "Segoe UI")

        

        self.setObjectName("SettingsSidebar")  # если ещё не стоит
        self.setStyleSheet(self._qss())


        # ── Каркас
        self.setFixedWidth(self._panel_width)
        outer = QVBoxLayout(self); outer.setContentsMargins(12, 12, 12, 12); outer.setSpacing(10)

        # ── Шапка (только иконки)
        header = QHBoxLayout(); header.setSpacing(8); header.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel("Меню"); self.lbl_title.setObjectName("SidebarTitle")
        header.addWidget(self.lbl_title); header.addStretch(1)

        self.tab_group = self._make_tabs(header)

        # Кнопка "Закрыть"
        btn_close = QPushButton(); btn_close.setObjectName("iconBtn")
        btn_close.setIcon(self._icon("x.svg")); btn_close.setIconSize(QSize(18, 18))
        btn_close.setFixedSize(19, 19); btn_close.setToolTip("Закрыть")
        btn_close.clicked.connect(self.hide_with_anim)
        header.addWidget(btn_close)
        outer.addLayout(header)

        # ── Страницы
        self.stack = QStackedLayout()
        outer.addLayout(self.stack, 1)

        # Стр. 0: Меню (вертикальная колонка иконок) — аккуратная карточка
        self._build_menu_page()

        # Стр. 1: Настройки (GX: свитчи и пресеты)
        self._build_settings_page()

        # Инициализация
        self._switch_page(0)
        self._load_from_qsettings()
        self.apply_theme_from_anchor()
        self._place_offscreen()
        self.hide()

        if anchor:
            anchor.installEventFilter(self)



    # ────────────────────────── Публичное API ──────────────────────────
    def set_anchor(self, anchor: QWidget) -> None:
        """Пере-якорить панель на новый контейнер (новая активная вкладка)."""
        if anchor is self._anchor or not isinstance(anchor, QWidget):
            return
        if self._anchor:
            try: self._anchor.removeEventFilter(self)
            except Exception: pass
        self._anchor = anchor
        self.setParent(anchor)
        self._place_offscreen()
        self.apply_theme_from_anchor()
        anchor.installEventFilter(self)

    def set_profile(self, profile: QWebEngineProfile) -> None:
        self._profile = profile

    def show_menu(self, actions: Sequence[Tuple[str, NoArgVoid, Optional[Union[str, QIcon]]]], title: str = "Меню") -> None:
        """
        actions: (label, callback, icon_name_or_path)
        Иконки обязательны. label уходит в tooltip.
        """
        self.lbl_title.setText(title)
        self._rebuild_menu(actions)
        self._switch_page(0)
        self.show_with_anim()

    def show_settings(self, title: str = "Настройки") -> None:
        self.lbl_title.setText(title)
        self._switch_page(1)
        self.show_with_anim()

    # ────────────────────────── UI builders ───────────────────────────
    def _make_tabs(self, header_layout: QHBoxLayout):
        from PyQt5.QtWidgets import QButtonGroup
        tab_group = QButtonGroup(self)

        self.btn_tab_menu = QPushButton(); self.btn_tab_menu.setObjectName("tabBtn")
        self.btn_tab_menu.setCheckable(True); self.btn_tab_menu.setChecked(True)
        self.btn_tab_menu.setIcon(self._icon("menu.svg")); self.btn_tab_menu.setIconSize(QSize(18, 18))
        self.btn_tab_menu.setFixedSize(32, 32); self.btn_tab_menu.setToolTip("Меню")
        tab_group.addButton(self.btn_tab_menu, 0)
        self.btn_tab_menu.clicked.connect(lambda: self._switch_page(0))

        self.btn_tab_settings = QPushButton(); self.btn_tab_settings.setObjectName("tabBtn")
        self.btn_tab_settings.setCheckable(True)
        self.btn_tab_settings.setIcon(self._icon("settings.png")); self.btn_tab_settings.setIconSize(QSize(18, 18))
        self.btn_tab_settings.setFixedSize(32, 32); self.btn_tab_settings.setToolTip("Настройки")
        tab_group.addButton(self.btn_tab_settings, 1)
        self.btn_tab_settings.clicked.connect(lambda: self._switch_page(1))

        tabs = QHBoxLayout(); tabs.setSpacing(6)
        tabs.addWidget(self.btn_tab_menu); tabs.addWidget(self.btn_tab_settings)
        header_layout.addLayout(tabs)
        return tab_group

    def _build_menu_page(self):
        self.page_menu = QFrame(); self.page_menu.setObjectName("MenuCard")
        pm = QVBoxLayout(self.page_menu); pm.setContentsMargins(10, 10, 10, 10); pm.setSpacing(10)

        self.menu_area = QScrollArea(self.page_menu); self.menu_area.setObjectName("menuArea")
        self.menu_area.setFrameShape(QFrame.NoFrame)
        self.menu_area.setWidgetResizable(True)
        self.menu_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.menu_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.menu_area.viewport().setObjectName("menuViewport")

        self._menu_container = QWidget(); self._menu_container.setObjectName("menuContainer")
        self._menu_layout = QVBoxLayout(self._menu_container)
        self._menu_layout.setContentsMargins(2, 2, 2, 2)
        self._menu_layout.setSpacing(10)
        self._menu_layout.setAlignment(Qt.AlignTop)

        self.menu_area.setWidget(self._menu_container)
        pm.addWidget(self.menu_area, 1)
        self.stack.addWidget(self.page_menu)

    def _build_settings_page(self):
        self.page_settings = QWidget()
        ps = QVBoxLayout(self.page_settings); ps.setContentsMargins(0, 0, 0, 0); ps.setSpacing(10)

        # Тема — из вкладки (показываем метку)
        row_theme = QHBoxLayout()
        row_theme.addWidget(QLabel("Тема:"))
        lab = QLabel("из вкладки"); lab.setObjectName("Muted")
        row_theme.addWidget(lab); row_theme.addStretch(1)
        ps.addLayout(row_theme)

        # Домашняя
        self.ed_home = QLineEdit(); self.ed_home.setPlaceholderText("http://127.0.0.1:5000/")
        ps.addLayout(self._row(QLabel("Домашняя:"), self.ed_home))

        # Поиск
        self.cb_engine = QComboBox(); self.cb_engine.addItems(["Google", "Yandex", "DuckDuckGo", "Bing", "Custom"])
        self.ed_custom = QLineEdit(); self.ed_custom.setPlaceholderText("https://example.com/search?q={query}")
        self.cb_engine.currentTextChanged.connect(self._update_custom_visibility)
        ps.addLayout(self._row(QLabel("Поиск:"), self.cb_engine)); ps.addWidget(self.ed_custom)

        # Файлы
        ps.addWidget(self._section_divider("Файлы"))
        self.ed_downloads = QLineEdit(); self.ed_downloads.setPlaceholderText("Папка загрузок…")
        btn_browse = QPushButton("Обзор…"); btn_browse.clicked.connect(self._pick_downloads_dir)
        row_dl = QHBoxLayout(); row_dl.addWidget(self.ed_downloads, 1); row_dl.addWidget(btn_browse)
        ps.addLayout(row_dl)

        # Оформление (GX переключатели)
        ps.addWidget(self._section_divider("Оформление"))
        self.sw_show_sidebar = GxSwitch(checked=True, accent=self._accent)
        self.sw_force_dark   = GxSwitch(checked=False, accent=self._accent)
        ps.addLayout(self._row(QLabel("Показывать боковую панель"), self.sw_show_sidebar))
        ps.addLayout(self._row(QLabel("Тёмная тема для сайтов"), self.sw_force_dark))

        # Пресеты акцента
        ps.addWidget(self._section_divider("Акцент (цвет)"))

        # — данные категорий
        s = QSettings(ORG, APP)
        self._recent_accents = s.value("recent_accents", [], type=list) or []

        ACCENT_CATEGORIES = {
            "Современные": [
                ("Futuristic", "#00BFFF"),
                ("Solarized Blue", "#268BD2"),
                ("Matrix Green", "#00FF00"),
                ("Turbine Teal", "#10E0C0"),
            ],
            "Классика": [
                ("Lambda", "#FF7A00"),
                ("Coming Soon", "#FFD400"),
                ("Crimson", "#DC143C"),
                ("Deep Purple", "#8A2BE2"),
                ("Royal Blue", "#4169E1"),
            ],
            "Нейтральные": [
                ("Monochrome", "#AAAAAA"),
                ("Graphite", "#2F4F4F"),
                ("Slate", "#708090"),
                ("Charcoal", "#36454F"),
            ],
            "Пастель": [
                ("Pastel Pink", "#FFB6C1"),
                ("Mint", "#98FF98"),
                ("Sky", "#87CEFA"),
                ("Peach", "#FFCBA4"),
            ],
            "Последние": [(c, c) for c in self._recent_accents],
        }

        def _normalize_hex(h: str) -> str:
            return QColor(h).name(QColor.HexRgb).upper()

        def _make_color_icon(hex_color: str, size: int = 16) -> QIcon:
            pm = QPixmap(size, size); pm.fill(Qt.transparent)
            p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
            r = pm.rect().adjusted(1, 1, -1, -1)
            p.setBrush(QColor(hex_color)); p.setPen(QPen(QColor(0,0,0,40), 1))
            p.drawEllipse(r); p.end()
            return QIcon(pm)

        def _save_recent():
            QSettings(ORG, APP).setValue("recent_accents", self._recent_accents)

        def _update_recent(hx: str, limit: int = 8):
            hx = _normalize_hex(hx)
            self._recent_accents = [c for c in self._recent_accents if _normalize_hex(c) != hx]
            self._recent_accents.insert(0, hx)
            self._recent_accents = self._recent_accents[:limit]
            _save_recent()

        def _populate_colors(cat: str):
            self.accent_combo.blockSignals(True)
            self.accent_combo.clear()
            items = ACCENT_CATEGORIES.get(cat, [])
            if cat == "Последние":
                items = [(c, c) for c in self._recent_accents]
            for name, hx in items:
                self.accent_combo.addItem(_make_color_icon(hx), f"{name}  {hx}", userData=_normalize_hex(hx))
                idx = self.accent_combo.count() - 1
                self.accent_combo.setItemData(idx, f"{name} — {hx}", Qt.ToolTipRole)
            if self.accent_combo.count() > 0:
                self.accent_combo.addItem("──────────")
                sep = self.accent_combo.model().item(self.accent_combo.count() - 1)
                if sep: sep.setEnabled(False)
            self.accent_combo.addItem("🎨 Выбрать цвет…", userData="__custom__")
            self.accent_combo.blockSignals(False)

        def _update_preview(hx: str):
            self.accent_preview.setStyleSheet(
                f"border:1px solid rgba(0,0,0,.25); border-radius:6px; background:{_normalize_hex(hx)};"
            )

        def _select_in_ui(hx: str):
            hx = _normalize_hex(hx)
            for cat, pairs in ACCENT_CATEGORIES.items():
                for _, c in pairs:
                    if _normalize_hex(c) == hx:
                        self.accent_category_combo.setCurrentText(cat)
                        _populate_colors(cat)
                        j = self.accent_combo.findData(hx)
                        if j >= 0: self.accent_combo.setCurrentIndex(j)
                        _update_preview(hx)
                        return
            _update_recent(hx)
            self.accent_category_combo.setCurrentText("Последние")
            _populate_colors("Последние")
            j = self.accent_combo.findData(hx)
            if j < 0:
                self.accent_combo.insertItem(0, _make_color_icon(hx), hx, userData=hx)
                j = 0
            self.accent_combo.setCurrentIndex(j)
            _update_preview(hx)

        def _on_cat_changed(cat: str):
            _populate_colors(cat)
            cur = getattr(self, "_accent", "#00BFFF")
            j = self.accent_combo.findData(_normalize_hex(cur))
            if j >= 0: self.accent_combo.setCurrentIndex(j)
            _update_preview(cur)

        def _on_color_chosen(idx: int):
            data = self.accent_combo.itemData(idx)
            if data == "__custom__":
                start = QColor(getattr(self, "_accent", "#00BFFF"))
                color = QColorDialog.getColor(start, self, "Выбор акцентного цвета")
                if color.isValid():
                    hx = color.name(QColor.HexRgb).upper()
                    self._set_accent(hx)
                    _update_recent(hx)
                    _select_in_ui(hx)
                else:
                    _select_in_ui(getattr(self, "_accent", "#00BFFF"))
                return
            if isinstance(data, str) and data.startswith("#"):
                hx = _normalize_hex(data)
                self._set_accent(hx)
                _update_recent(hx)
                _update_preview(hx)

        # — Виджеты: Категория | Цвет | Превью
        row_cat = QHBoxLayout()
        row_cat.addWidget(QLabel("Категория:"))
        self.accent_category_combo = QComboBox(self)
        self.accent_category_combo.addItems([k for k in ACCENT_CATEGORIES.keys() if k != "Последние"] + ["Последние"])
        self.accent_category_combo.setMinimumContentsLength(14)
        self.accent_category_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        row_cat.addWidget(self.accent_category_combo, 1)
        ps.addLayout(row_cat)

        row_color = QHBoxLayout()
        row_color.addWidget(QLabel("Цвет:"))
        self.accent_combo = QComboBox(self)
        self.accent_combo.setView(QListView())
        self.accent_combo.setEditable(True)                    # поиск по подстроке
        self.accent_combo.setInsertPolicy(QComboBox.NoInsert)
        self.accent_combo.completer().setFilterMode(Qt.MatchContains)
        self.accent_combo.completer().setCompletionMode(QCompleter.PopupCompletion)
        self.accent_combo.setIconSize(QSize(16, 16))
        self.accent_combo.setMinimumContentsLength(18)
        self.accent_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.accent_combo.setStyleSheet("QComboBox { padding: 6px 10px; } QComboBox QAbstractItemView::item { padding: 6px 8px; }")
        row_color.addWidget(self.accent_combo, 1)

        self.accent_preview = QFrame(self)
        self.accent_preview.setFixedSize(44, 22)
        self.accent_preview.setStyleSheet("border:1px solid rgba(0,0,0,.25); border-radius:6px;")
        row_color.addWidget(self.accent_preview)
        ps.addLayout(row_color)

        # — Сигналы/инициализация
        self.accent_category_combo.currentTextChanged.connect(_on_cat_changed)
        self.accent_combo.activated.connect(_on_color_chosen)

        default_accent = getattr(self, "_accent", "#22D3EE")
        _populate_colors("Современные")
        _select_in_ui(default_accent)

        # --- Шрифты для браузера (улучшенный комбобокс) ---
        ps.addWidget(self._section_divider("Шрифты для браузера"))

        font_combo = QComboBox(self)
        font_combo.setView(QListView()); font_combo.setEditable(True)
        font_combo.setInsertPolicy(QComboBox.NoInsert)
        font_combo.completer().setFilterMode(Qt.MatchContains)
        font_combo.completer().setCompletionMode(QCompleter.PopupCompletion)

        fonts = [
            "Segoe UI", "Arial", "Helvetica", "Roboto", "Open Sans",
            "Times New Roman", "Georgia",
            "Consolas", "Courier New", "Monaco",
        ]
        for fam in fonts:
            font_combo.addItem(fam)
            idx = font_combo.count() - 1
            font_combo.setItemData(idx, QFont(fam), Qt.FontRole)
            font_combo.setItemData(idx, fam, Qt.ToolTipRole)

        current_font = getattr(self, "_font", "Segoe UI")
        i = font_combo.findText(current_font)
        if i >= 0: font_combo.setCurrentIndex(i)

        font_combo.currentTextChanged.connect(lambda f: self._set_font(f))
        ps.addWidget(font_combo)

        # Медиа
        ps.addWidget(self._section_divider("Медиа"))
        self.chk_mute_bg = QCheckBox("Выключать звук фоновых вкладок")
        self.chk_require_gesture = QCheckBox("Требовать жест для автоплея")
        ps.addWidget(self.chk_mute_bg); ps.addWidget(self.chk_require_gesture)

        # Приватность
        row_priv = QHBoxLayout()

        btn_cache   = QPushButton("Очистить кэш")
        btn_cookies = QPushButton("Очистить cookies")
        btn_storage = QPushButton("Очистить DOM-хранилища")
        btn_all     = QPushButton("Очистить всё (кэш+cookies+DOM)")

        btn_cache.clicked.connect(self._clear_cache)
        btn_cookies.clicked.connect(self._clear_cookies)
        btn_storage.clicked.connect(self._clear_storage)
        btn_all.clicked.connect(self._clear_all_privacy)

        row_priv.addWidget(btn_cache)
        row_priv.addWidget(btn_cookies)
        row_priv.addWidget(btn_storage)
        row_priv.addWidget(btn_all)

        ps.addLayout(row_priv)


        ps.addItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        actions = QHBoxLayout()
        self.btn_reset = QPushButton("Сброс"); self.btn_apply = QPushButton("Применить")
        actions.addStretch(1); actions.addWidget(self.btn_reset); actions.addWidget(self.btn_apply)
        self.btn_apply.clicked.connect(self._apply_and_emit); self.btn_reset.clicked.connect(self._reset_to_defaults)
        ps.addLayout(actions)

        self.stack.addWidget(self.page_settings)

    # ────────────────────────── Вспомогательное ───────────────────────
    def _row(self, left_w: QWidget, right_w: QWidget) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(8); row.addWidget(left_w); row.addStretch(1); row.addWidget(right_w)
        return row




    
    def _icon(self, path: str) -> QIcon:
        """Умный поиск иконки с кэшем, алиасами и расширенным набором базовых путей.
           Возвращает заглушку, если файл не найден (без спама в лог).
        """
        if not path:
            return QIcon()

        # кэш быстрых попаданий/промахов
        if path in _ICON_CACHE:
            return _ICON_CACHE[path]
        if _ICON_MISS.get(path):
            return _fallback_icon_pixmap()

        # Qt resource и абсолютные пути
        if str(path).startswith(":/"):
            ic = QIcon(path)
            _ICON_CACHE[path] = ic
            return ic
        if os.path.isabs(path):
            if os.path.exists(path):
                ic = QIcon(path)
                _ICON_CACHE[path] = ic
                return ic
            _ICON_MISS[path] = True
            return _fallback_icon_pixmap()

        base_in = path
        # алиасы (svg↔png, старые имена)
        path = _ICON_ALIASES.get(path, path)

        # подготовим кандидаты с/без расширения
        rels = []
        root, ext = os.path.splitext(path)
        if ext:
            rels.append(path)
        else:
            rels += [root + ".svg", root + ".png"]

        # если не указан явный префикс — добавим icons/, img/icons/, modules/icons/
        def needs_prefix(p: str) -> bool:
            return not (p.startswith("icons/") or p.startswith("img/icons/") or p.startswith("modules/icons/"))
        candidates = list(rels)
        for p in list(rels):
            if needs_prefix(p):
                candidates += [f"icons/{p}", f"img/icons/{p}", f"modules/icons/{p}"]
        if needs_prefix(path):
            candidates += [f"icons/{path}", f"img/icons/{path}", f"modules/icons/{path}"]

        # корни: cwd (=_internal), каталог модуля, корень проекта
        roots = [
            os.getcwd(),
            os.path.abspath(os.path.join(os.path.dirname(__file__))),           # .../modules
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),     # .../ (корень)
        ]

        for rel in candidates:
            for r in roots:
                p = os.path.join(r, rel)
                ap = self._asset(p) if getattr(self, "_asset", None) else p
                if os.path.exists(ap):
                    ic = QIcon(ap)
                    _ICON_CACHE[base_in] = ic
                    return ic

        _ICON_MISS[base_in] = True
        return _fallback_icon_pixmap()

    def _section_divider(self, title: str) -> QWidget:
        box = QWidget(); box.setObjectName("SectionDivider")
        lay = QHBoxLayout(box); lay.setContentsMargins(0, 6, 0, 6); lay.setSpacing(8)
        lbl = QLabel(title); lbl.setObjectName("SectionLabel")
        line = QWidget(); line.setObjectName("Hairline"); line.setFixedHeight(1)
        lay.addWidget(lbl); lay.addWidget(line, 1)
        return box

    def _rebuild_menu(self, actions=None) -> None:
        # Очистка контейнера
        for i in reversed(range(self._menu_layout.count())):
            w = self._menu_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import QMessageBox, QToolButton, QWidget, QLabel

        def br():
            return self.window()

        def run(cb):
            try:
                self.hide_with_anim()
                QTimer.singleShot(120, cb)
            except Exception:
                cb()

        def make_btn(tt: str, icon_name: str, cb, *, checkable=False, checked=False, toggle_name="ToggleIcon") -> QToolButton:
            btn = QToolButton()
            btn.setObjectName(toggle_name if checkable else "MenuIcon")
            btn.setAutoRaise(False)
            btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
            btn.setFixedSize(44, 44)
            btn.setIconSize(QSize(22, 22))
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFocusPolicy(Qt.StrongFocus)
            btn.setToolTip(tt)
            btn.setIcon(self._icon(icon_name))
            if checkable:
                btn.setCheckable(True)
                btn.setChecked(bool(checked))
                btn.toggled.connect(lambda _state: run(cb))
            else:
                btn.clicked.connect(lambda: run(cb))
            return btn

        def section(title: str):
            box = QWidget(); box.setObjectName("MenuSection")
            lay = QVBoxLayout(box); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(6)
            cap = QLabel(title); cap.setObjectName("SectionTitle"); lay.addWidget(cap)
            grid_host = QWidget(); grid_host.setObjectName("GridHost")
            lay_grid = QGridLayout(grid_host)
            lay_grid.setContentsMargins(0, 0, 0, 0)
            lay_grid.setHorizontalSpacing(8)
            lay_grid.setVerticalSpacing(8)
            lay.addWidget(grid_host)
            return box, lay_grid

        def add_buttons(grid_layout, btns, columns=4):
            for idx, b in enumerate(btns):
                r, c = divmod(idx, columns)
                grid_layout.addWidget(b, r, c, Qt.AlignLeft)

        # ── Текущее состояние
        B = br()
        is_dark   = self._is_dark()
        is_muted  = bool(getattr(B, "_global_muted", False))
        proxy_on  = bool(getattr(B, "_proxy_enabled", False) or callable(getattr(B, "is_proxy_enabled", None)) and B.is_proxy_enabled())
        offline   = bool(getattr(B, "_offline_mode", False) or callable(getattr(B, "is_offline", None)) and B.is_offline())

        # ── Экшены (ровно один раз определяем все коллбэки) ───────────────
        def act_toggle_theme():
            want_dark = not self._is_dark()
            try:
                if callable(getattr(B, "apply_global_theme", None)):
                    B.apply_global_theme(bool(want_dark))
                else:
                    self.apply_theme_from_anchor()
            finally:
                QSettings("SalemCorp", "SalemExplorer").setValue("force_dark", bool(want_dark))
                QTimer.singleShot(60, lambda: self._rebuild_menu())

        def act_toggle_mute():
            try:
                from PyQt5.QtWebEngineWidgets import QWebEngineView
                B._global_muted = not bool(getattr(B, "_global_muted", False))
                tabs = getattr(B, "tabs", None)
                if tabs:
                    for i in range(tabs.count()):
                        w = tabs.widget(i)
                        if isinstance(w, QWebEngineView):
                            try: w.page().setAudioMuted(B._global_muted)
                            except Exception: pass
            finally:
                QTimer.singleShot(60, lambda: self._rebuild_menu())

        def act_toggle_proxy():
            fn = getattr(B, "toggle_proxy", None) or getattr(B, "set_proxy_enabled", None)
            try:
                if callable(fn):
                    if fn.__code__.co_argcount >= 2:
                        enabled = not bool(getattr(B, "_proxy_enabled", False))
                        fn(enabled); B._proxy_enabled = enabled
                    else:
                        fn(); B._proxy_enabled = not bool(getattr(B, "_proxy_enabled", False))
                else:
                    QMessageBox.information(self, "Proxy/VPN", "Переключатель Proxy/VPN не реализован.")
            finally:
                QTimer.singleShot(60, lambda: self._rebuild_menu())
                

        def act_toggle_offline():
            try:
                if callable(getattr(B, "set_offline_mode", None)):
                    new_state = not bool(getattr(B, "_offline_mode", False))
                    B.set_offline_mode(new_state); B._offline_mode = new_state
                else:
                    B._offline_mode = not bool(getattr(B, "_offline_mode", False))
            finally:
                QTimer.singleShot(60, lambda: self._rebuild_menu())

        def act_home():
            fn = getattr(B, "navigate_home", None)
            if callable(fn): fn()

        def act_bookmarks():
            bb = getattr(B, "bookmarks_bar", None)
            if bb and callable(getattr(bb, "toggle", None)): bb.toggle()

        def act_history():
            if callable(getattr(B, "open_history_tab", None)):
                B.open_history_tab()
        
        def act_downloads():
            if callable(getattr(B, "open_downloads_tab", None)):
                B.open_downloads_tab()

        def act_extensions():
            fn = (getattr(B, "open_extensions_window", None)
                  or getattr(B, "open_extensions_manager_tab", None)
                  or getattr(B, "open_extensions_tab", None))
            if callable(fn):
                fn()
                return
        
            # fallback через роутер спец-URL
            open_url = (getattr(B, "add_new_tab", None)
                        or getattr(B, "open_url_in_new_tab", None)
                        or getattr(B, "navigate_to_url", None))
            if callable(open_url):
                try:
                    open_url("ext://extensions")
                except TypeError:
                    open_url("ext://extensions", "Расширения")
                return
        
            # последний шанс — всплывающее окно
            popup = getattr(B, "open_extensions_popup", None)
            if callable(popup):
                popup()


        def act_restart():
            import sys, os
            from PyQt5.QtCore import QProcess
            try:
                QProcess.startDetached(sys.executable, [os.path.abspath(sys.argv[0])] + sys.argv[1:], os.getcwd())
            finally:
                B.close()

        def act_clear_cache():
            try: self._clear_cache()
            except Exception: pass

        def act_profile():
            fn = getattr(B, "enable_user_account", None) or getattr(B, "open_profile", None)
            if callable(fn): fn()

        def act_open_settings():
            self.show_settings("Настройки")

        def act_pick_accent():
            from PyQt5.QtWidgets import QColorDialog
            start = QColor(getattr(self, "_accent", "#22D3EE"))
            color = QColorDialog.getColor(start, self, "Выбор акцентного цвета")
            if color.isValid():
                try: self._set_accent(color.name(QColor.HexRgb).upper())
                except Exception:
                    QSettings("SalemCorp", "SalemExplorer").setValue("accent_color", color.name(QColor.HexRgb).upper())
                    self.apply_theme_from_anchor()

        def act_pick_font():
            try:
                from PyQt5.QtWidgets import QFontDialog
                font, ok = QFontDialog.getFont(QFont(getattr(self, "_font", "Segoe UI")), self, "Выбор шрифта интерфейса")
                if ok:
                    fam = font.family()
                    try: self._set_font(fam)
                    except Exception:
                        QSettings("SalemCorp", "SalemExplorer").setValue("ui_font", fam)
                        self.apply_theme_from_anchor()
            except Exception:
                self.show_settings("Шрифты")

        def act_zoom_menu():
            fn = getattr(B, "zoom_menu", None) or getattr(B, "show_zoom_menu", None)
            if callable(fn): fn()

        def act_exit():
            fn = getattr(B, "safe_exit", None) or getattr(B, "close", None)
            if callable(fn): fn()

        # ── Секции ────────────────────────────────────────────────────────
        # 1) Системные
        sec1, grid1 = section("Системные")
        btn_theme   = make_btn("Тёмная/светлая тема", "sun.png" if is_dark else "moon.png", act_toggle_theme,
                               checkable=True, checked=is_dark)
        btn_mute    = make_btn("Mute / Unmute", "volume-on.png" if is_muted else "volume-off.png", act_toggle_mute,
                               checkable=True, checked=is_muted)
        btn_vpn     = make_btn("VPN / Proxy", "lock.png" if proxy_on else "lock.png", act_toggle_proxy,
                               checkable=True, checked=proxy_on)
        btn_offline = make_btn("Offline Mode (кэш)", "offline.svg" if offline else "online.svg", act_toggle_offline,
                               checkable=True, checked=offline)
        add_buttons(grid1, [btn_theme, btn_mute, btn_vpn, btn_offline], columns=4)
        self._menu_layout.addWidget(sec1)

        # 2) Навигация
        sec2, grid2 = section("Навигация")
        btn_home  = make_btn("Домашняя", "home.png", act_home)
        btn_book  = make_btn("Закладки", "bookmarks.png", act_bookmarks)
        btn_hist  = make_btn("История", "history.png", act_history)
        btn_down  = make_btn("Загрузки", "download.png", act_downloads)
        btn_ext = make_btn("Расширения", "addons.png", act_extensions)
        btn_mods  = make_btn("Моды", "modes.svg", self.act_mods)
        add_buttons(grid2, [btn_home, btn_book, btn_hist, btn_ext, btn_down, btn_mods], columns=4)
        self._menu_layout.addWidget(sec2)

        # 3) Действия
        sec3, grid3 = section("Действия")
        btn_restart = make_btn("Перезапустить браузер", "restart.png", act_restart)
        btn_clear   = make_btn("Очистить кэш", "broom.png", act_clear_cache)
        btn_clear_all = make_btn("Очистить всё (кэш+cookies+хранилище)", "trash.png",
                         self._clear_all_privacy)
        btn_profile = make_btn("Профиль", "profile.png", act_profile)
        btn_sets    = make_btn("Настройки", "settings.png", act_open_settings)
        self.btn_exit = make_btn("Выйти из браузера", "power.png", act_exit)
        add_buttons(grid3, [btn_restart, btn_clear, btn_clear_all, btn_profile, btn_sets, self.btn_exit], columns=5)
        self._menu_layout.addWidget(sec3)

        # 4) UI
        sec4, grid4 = section("UI")
        btn_accent = make_btn("Акцентный цвет", "colors.png", act_pick_accent)
        btn_font   = make_btn("Выбор шрифта", "fonts.png", act_pick_font)
        btn_zoom   = make_btn("Масштаб", "zoom.svg", act_zoom_menu)
        add_buttons(grid4, [btn_accent, btn_font, btn_zoom], columns=4)
        self._menu_layout.addWidget(sec4)

        self._menu_layout.addStretch(1)



    # ────────────────────────── Табы / Показ ──────────────────────────
    def _switch_page(self, index: int) -> None:
        idx = 0 if index <= 0 else 1
        self.stack.setCurrentIndex(idx)
        self.btn_tab_menu.setChecked(idx == 0)
        self.btn_tab_settings.setChecked(idx == 1)
        self.lbl_title.setText("Меню" if idx == 0 else "Настройки")

    def toggle(self) -> None:
        self.hide_with_anim() if self.isVisible() else self.show_with_anim()

    def show_with_anim(self) -> None:
        if not self._anchor: return
        self.show(); self.raise_()
        pw = self._anchor.width(); ph = self._anchor.height()
        start = QRect(pw, 0, self._panel_width, ph)
        end   = QRect(pw - self._panel_width, 0, self._panel_width, ph)
        self.setGeometry(start)
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(200); anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.setStartValue(start); anim.setEndValue(end)
        anim.start(); self._anim = anim

    def hide_with_anim(self) -> None:
        if not (self._anchor and self.isVisible()): return
        pw = self._anchor.width(); ph = self._anchor.height()
        start = self.geometry()
        end   = QRect(pw, 0, self._panel_width, ph)
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(160); anim.setEasingCurve(QEasingCurve.InCubic)
        anim.setStartValue(start); anim.setEndValue(end)
        def _after():
            self.hide(); self.closed.emit()
        anim.finished.connect(_after); anim.start(); self._anim = anim

    def _place_offscreen(self) -> None:
        if not self._anchor: return
        self.setGeometry(self._anchor.width(), 0, self._panel_width, self._anchor.height())

    # ────────────────────────── События / Тема ────────────────────────
    def eventFilter(self, obj, ev):
        if obj is self._anchor and ev.type() in (QEvent.Resize, QEvent.Move, QEvent.Show):
            if self.isVisible():
                self.setGeometry(self._anchor.width()-self._panel_width, 0, self._panel_width, self._anchor.height())
            else:
                self._place_offscreen()
        if obj is self._anchor and ev.type() == QEvent.PaletteChange:
            self.apply_theme_from_anchor()
        return super().eventFilter(obj, ev)

    def _is_dark(self) -> bool:
        p = (self._anchor.palette() if self._anchor else self.palette())
        c = p.window().color()
        lightness = (max(c.red(), c.green(), c.blue()) + min(c.red(), c.green(), c.blue())) / 510.0
        return lightness < 0.5

    def apply_theme_from_anchor(self) -> None:
        # обновляем QSS
        self.setStyleSheet(self._qss())
        # и перекрашиваем свитчи под свежий акцент
        accent = getattr(self, "_accent", "#22d3ee")
        if hasattr(self, "sw_show_sidebar"): self.sw_show_sidebar.setAccent(accent)
        if hasattr(self, "sw_force_dark"):   self.sw_force_dark.setAccent(accent)

    # ────────────────────────── Settings I/O ─────────────────────────
    def _load_from_qsettings(self) -> None:
        s = QSettings(ORG, APP)
        self.ed_home.setText(s.value("home_url", "http://127.0.0.1:5000/"))
        self.cb_engine.setCurrentText(s.value("search_engine", "Google"))
        self.ed_custom.setText(s.value("search_custom", ""))
        self.ed_downloads.setText(s.value("downloads_dir", ""))
        self.chk_mute_bg.setChecked(s.value("mute_background", True, type=bool))
        self.chk_require_gesture.setChecked(s.value("require_gesture", False, type=bool))
        self.sw_show_sidebar.setChecked(s.value("show_sidebar", True, type=bool))
        self.sw_force_dark.setChecked(s.value("force_dark", False, type=bool))
        self._font = QSettings(ORG, APP).value("ui_font", "Segoe UI")
        self._update_custom_visibility()

    def _save_to_qsettings(self, data: Dict) -> None:
        s = QSettings(ORG, APP)
        for k, v in data.items():
            s.setValue(k, v)

    def _collect(self) -> Dict:
        return {
            "home_url": self.ed_home.text().strip(),
            "search_engine": self.cb_engine.currentText(),
            "search_custom": self.ed_custom.text().strip(),
            "downloads_dir": self.ed_downloads.text().strip(),
            "mute_background": self.chk_mute_bg.isChecked(),
            "require_gesture": self.chk_require_gesture.isChecked(),
            "show_sidebar": self.sw_show_sidebar.isChecked(),
            "force_dark": self.sw_force_dark.isChecked(),
        }

    def _apply_and_emit(self) -> None:
        data = self._collect()
        self._save_to_qsettings(data)
        try:
            QWebEngineSettings.globalSettings().setAttribute(
                QWebEngineSettings.PlaybackRequiresUserGesture,
                bool(data.get("require_gesture", False))
            )
        except Exception:
            pass
        data["accent_color"] = self._accent
        self.apply_theme_from_anchor()
        self.settingsChanged.emit(data)

    def _reset_to_defaults(self) -> None:
        self.ed_home.setText("http://127.0.0.1:5000/")
        self.cb_engine.setCurrentText("Google")
        self.ed_custom.clear()
        self.chk_mute_bg.setChecked(True)
        self.chk_require_gesture.setChecked(False)
        self.ed_downloads.clear()
        self.sw_show_sidebar.setChecked(True)
        self.sw_force_dark.setChecked(False)
        self._apply_and_emit()

    def _pick_downloads_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Папка для загрузок")
        if path: self.ed_downloads.setText(path)

    def _update_custom_visibility(self) -> None:
        self.ed_custom.setVisible(self.cb_engine.currentText().lower() == "custom")

    def _set_accent(self, hex_color: str):
        self._accent = hex_color
        QSettings(ORG, APP).setValue("accent_color", hex_color)
        # обновим стили локально
        self.apply_theme_from_anchor()
        # эмитим наверх
        data = self._collect(); data["accent_color"] = hex_color
        self.settingsChanged.emit(data)

    def _set_font(self, font_family: str) -> None:
        font_family = (font_family or "Segoe UI").strip()
        if getattr(self, "_font", None) == font_family:
            return
        self._font = font_family
        QSettings(ORG, APP).setValue("ui_font", font_family)
        # локально перерисуем панель под новый шрифт
        self.apply_theme_from_anchor()
        # отдаём наверх — включаем и шрифт, и акцент
        data = self._collect()
        data["accent_color"] = getattr(self, "_accent", "#22d3ee")
        data["ui_font"] = self._font
        self.settingsChanged.emit(data)

    # ────────────────────────── Actions ──────────────────────────
    def act_mods(self):
        """Open the mods manager tab or navigate to the mods page."""
        B = self.window()  # Get the browser window
        # 1) If there's a method to open the mods tab, use it
        fn = getattr(B, "open_mods_manager_tab", None)
        if callable(fn):
            fn()
            return
        # 2) Otherwise, try a "fake" URL — let the router handle it
        nav = (getattr(B, "navigate_to_url", None)
               or getattr(B, "load_url", None)
               or getattr(B, "open_url", None))
        if callable(nav):
            nav("salem://mods")
            return
        # 3) Last resort: open in a new tab, if such a method exists
        newtab = (getattr(B, "open_url_in_new_tab", None)
                  or getattr(B, "add_new_tab", None))
        if callable(newtab):
            try:
                newtab("salem://mods")
            except TypeError:
                # Some signatures require a title as well
                newtab("salem://mods", "Моды")
    
    def act_mods(self):
        B = self.window()  # окно браузера
        # 1) Если уже есть метод вкладки модов — используем его
        fn = getattr(B, "open_mods_manager_tab", None)
        if callable(fn):
            fn()
            return
        # 2) Иначе пробуем «фейковый» адрес — пусть роутер перехватит
        nav = (getattr(B, "navigate_to_url", None)
               or getattr(B, "load_url", None)
               or getattr(B, "open_url", None))
        if callable(nav):
            nav("salem://mods")
            return
        # 3) Последний шанс: открыть в новой вкладке, если есть такой метод
        newtab = (getattr(B, "open_url_in_new_tab", None)
                  or getattr(B, "add_new_tab", None))
        if callable(newtab):
            try:
                newtab("salem://mods")
            except TypeError:
                # некоторые сигнатуры требуют ещё заголовок
                newtab("salem://mods", "Моды")


    # ────────────────────────── Privacy ops ──────────────────────────
    def _clear_cache(self) -> None:
        try:
            if self._profile: self._profile.clearHttpCache()
        except Exception: pass

    def _clear_cookies(self) -> None:
        try:
            if self._profile: self._profile.cookieStore().deleteAllCookies()
        except Exception: pass

    def _clear_storage(self):
        if not self._profile:
            return
        try:
            import shutil, os
            storage_root = getattr(self._profile, "persistentStoragePath", lambda: "")()
            if not storage_root:
                return
            # Безопасно снести всё содержимое хранилища и пересоздать корень
            shutil.rmtree(storage_root, ignore_errors=True)
            os.makedirs(storage_root, exist_ok=True)
        except Exception:
            pass

    def _clear_all_privacy(self):
        self._clear_cache()
        self._clear_cookies()
        self._clear_storage()



    def _clear_history(self) -> None:
        try:
            if self._profile: self._profile.clearAllVisitedLinks()
        except Exception: pass

    def _qss(self) -> str:
        from PyQt5.QtGui import QColor
    
        dark = getattr(self, "_is_dark", lambda: True)()
        accent = getattr(self, "_accent", "#22d3ee")
        font_family = getattr(self, "_font", "Segoe UI")
        safe_font = '"' + str(font_family).replace('"', '\\"') + '"'
    
        def a255(x):
            try:
                f = float(x)
            except Exception:
                return 255
            return max(0, min(255, int(round(f * 255)))) if 0.0 <= f <= 1.0 else max(0, min(255, int(round(f))))
    
        def rgba255(r, g, b, a):
            return f"rgba({int(r)},{int(g)},{int(b)},{a255(a)})"
    
        _acc = QColor(accent)
        def acc_rgba(a):
            return rgba255(_acc.red(), _acc.green(), _acc.blue(), a)
    
        if not dark:
            bg, bg2, bg3, panel = "#ffffff", "#f6f7f9", "#eef1f6", "#f8fafc"
            text, text_muted = "#0f172a", "#475569"
            stroke  = rgba255(0, 0, 0, .12)
            stroke2 = rgba255(0, 0, 0, .18)
            stroke3 = rgba255(0, 0, 0, .28)
            scroll  = rgba255(0, 0, 0, .30)
            shadow_hint  = rgba255(0, 0, 0, .06)
            sel_text = "#0b1220"
        else:
            bg, bg2, bg3, panel = "#0f1115", "#141922", "#1b2232", "#0c0f15"
            text, text_muted = "#E7ECF6", "#A3ADC2"
            stroke  = rgba255(255, 255, 255, .10)
            stroke2 = rgba255(255, 255, 255, .16)
            stroke3 = rgba255(255, 255, 255, .22)
            scroll  = rgba255(255, 255, 255, .30)
            shadow_hint  = rgba255(0, 0, 0, .50)
            sel_text = "#0b1220"
    
        accent_rgba08 = acc_rgba(.08)
        accent_rgba12 = acc_rgba(.12)
        accent_rgba18 = acc_rgba(.18)
        accent_rgba24 = acc_rgba(.24)
        accent_hex    = _acc.name()
        accent_hex_l  = QColor(_acc).lighter(115).name()
        accent_hex_d  = QColor(_acc).darker(120).name()
    
        rgb_blue = "#6E9CFF"
        rgb_cyan = "#00FFEA"
        rgb_pink = "#FF0080"
    
        icon_fg        = text_muted
        icon_fg_hover  = text
        icon_fg_active = text
        icon_fg_muted  = text_muted
    
        qss = f"""
    * {{
      font-family: {safe_font};
      color: {text};
    }}
    QWidget {{ background: {bg}; }}
    QMainWindow, QDialog, QFrame {{ background: {bg}; border: none; }}
    QLabel {{ color: {text}; }}
    QLabel#Muted {{ color: {text_muted}; }}
    QLabel#SectionLabel {{ color: {text_muted}; font-weight: 700; }}
    #SidebarTitle {{ color: {text}; font-weight: 700; font-size: 15px; }}
    #SettingsSidebar {{ background: {panel}; border-left: 1px solid {stroke}; }}
    QFrame#MenuCard {{ background: {bg2}; border: 1px solid {stroke}; border-radius: 0px; }}
    QWidget#MenuSection {{ background: transparent; }}
    QWidget#GridHost {{ background: transparent; }}
    QWidget#SectionDivider {{ background: transparent; }}
    QWidget#Hairline {{ background: {stroke}; min-height: 1px; max-height: 1px; }}
    QLabel#SectionTitle {{
      color: {text_muted}; font-weight: 700; font-size: 12px; padding: 2px 8px;
      border: 1px solid {stroke}; border-radius: 0px; background: {bg2}; margin-bottom: 2px;
    }}
    QScrollArea#menuArea {{ border: none; background: transparent; }}
    #menuViewport {{ background: transparent; }}
    QToolButton#MenuIcon, QToolButton#ToggleIcon {{
      background: transparent;
      border: 1px solid {stroke};
      border-radius: 0px;
      padding: 9px;
      color: {icon_fg};
    }}
    QToolButton#MenuIcon:hover, QToolButton#ToggleIcon:hover {{
      background: {shadow_hint};
      border-color: {stroke2};
      color: {icon_fg_hover};
    }}
    QToolButton#MenuIcon:pressed, QToolButton#ToggleIcon:pressed {{
      padding-top: 10px; padding-left: 10px;
    }}
    QToolButton#MenuIcon:disabled, QToolButton#ToggleIcon:disabled {{ color: {icon_fg_muted}; }}
    QToolButton#ToggleIcon:checked {{
      background: {accent_rgba18};
      border-color: {accent_hex};
      color: {icon_fg_active};
    }}
    QToolButton#ToggleIcon:checked:hover {{ background: {accent_rgba24}; }}
    QToolButton#MenuIcon:focus, QToolButton#ToggleIcon:focus {{ border: 1px solid {accent_hex}; }}
    QPushButton#tabBtn {{
      background: transparent; color: {icon_fg}; border: 1px solid {stroke};
      border-radius: 0px; padding: 6px 10px;
    }}
    QPushButton#tabBtn:hover {{ border-color: {stroke2}; color: {icon_fg_hover}; }}
    QPushButton#tabBtn:checked {{ background: {accent_hex}; color: {sel_text}; border-color: {accent_hex}; }}
    QPushButton#iconBtn {{ background: transparent; border: 1px solid {stroke}; border-radius: 0px; color: {icon_fg}; }}
    QPushButton#iconBtn:hover {{ background: {shadow_hint}; color: {icon_fg_hover}; }}
    QPushButton#iconBtn:disabled {{ color: {icon_fg_muted}; }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateTimeEdit {{
      background: {bg2}; color: {text}; border: 1px solid {stroke}; border-radius: 0px; padding: 6px 10px;
      selection-background-color: {accent_rgba24}; selection-color: {sel_text};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateTimeEdit:focus {{
      border: 1px solid {accent_hex}; background: {bg3};
    }}
    QComboBox:focus {{ border: 1px solid {accent_hex}; background: {bg3}; }}
    QComboBox::drop-down {{ border-left: 1px solid {stroke}; width: 24px; margin: 0; border-radius: 0px; }}
    QComboBox::down-arrow {{ width: 10px; height: 10px; margin-right: 6px; }}
    QComboBox QAbstractItemView {{ background: {panel}; color: {text}; border: 1px solid {stroke2}; selection-background-color: {accent_rgba24}; selection-color: {sel_text}; }}
    QCheckBox, QRadioButton {{ color: {text}; spacing: 6px; }}
    QCheckBox::indicator, QRadioButton::indicator {{
      width: 16px; height: 16px; border: 1px solid {stroke2}; background: {bg2}; border-radius: 0px;
    }}
    QRadioButton::indicator {{ border-radius: 0px; }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent_hex}; }}
    QCheckBox::indicator:checked {{ background: {accent_hex}; border-color: {accent_hex}; }}
    QRadioButton::indicator:checked {{ background: {accent_hex}; border-color: {accent_hex}; }}
    QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {bg3}; border-color: {stroke}; }}
    QPushButton {{
      background: {bg2}; color: {text}; border: 1px solid {stroke};
      border-radius: 0px; padding: 3px 2px; font-weight: 700;
    }}
    QPushButton:hover {{ border-color: {stroke2}; background: {bg3}; }}
    QPushButton:pressed {{ padding-top: 7px; padding-left: 13px; }}
    QPushButton:disabled {{ color: {text_muted}; background: {bg3}; border-color: {stroke}; }}
    QPushButton#primary {{ background: {accent_hex}; color: {sel_text}; border-color: {accent_hex}; }}
    QPushButton#primary:hover {{ background: {accent_hex_l}; border-color: {accent_hex_l}; }}
    QPushButton#primary:pressed {{ background: {accent_hex_d}; border-color: {accent_hex_d}; }}
    QPushButton[destructive="true"] {{ background: #ff4d7a; color: #0b1220; border-color: #ff4d7a; }}
    QPushButton[destructive="true"]:hover {{ background: #ff6a93; border-color: #ff6a93; }}
    QPushButton[pill="true"] {{ border-radius: 0px; padding: 5px 10px; }}
    QTabWidget::pane {{ border: 1px solid {stroke}; background: {bg}; border-radius: 0px; }}
    QTabBar::tab {{ background: {bg2}; color: {text_muted}; border: 1px solid {stroke};
      padding: 6px 12px; border-radius: 0px; margin-right: 2px; }}
    QTabBar::tab:selected {{ background: {bg3}; color: {text}; border-color: {stroke2}; }}
    QTabBar::tab:hover {{ color: {text}; border-color: {stroke2}; }}
    QTabBar::close-button {{ width: 0; height: 0; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; margin: 2px 0 2px 0; }}
    QScrollBar::handle:vertical {{ background: {scroll}; border-radius: 0px; min-height: 24px; }}
    QScrollBar::handle:vertical:hover {{ background: {stroke3}; }}
    QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 0 2px 0 2px; }}
    QScrollBar::handle:horizontal {{ background: {scroll}; border-radius: 0px; min-width: 24px; }}
    QScrollBar::handle:horizontal:hover {{ background: {stroke3}; }}
    QSlider::groove:horizontal {{ height: 6px; background: {bg2}; border: 1px solid {stroke}; border-radius: 0px; }}
    QSlider::handle:horizontal {{ background: {accent_hex}; width: 14px; height: 14px; margin: -5px 0; border-radius: 0px; border: 1px solid {accent_hex}; }}
    QSlider::groove:vertical {{ width: 6px; background: {bg2}; border: 1px solid {stroke}; border-radius: 0px; }}
    QSlider::handle:vertical {{ background: {accent_hex}; width: 14px; height: 14px; margin: 0 -5px; border-radius: 0px; border: 1px solid {accent_hex}; }}
    QSlider::sub-page:horizontal, QSlider::add-page:vertical {{ background: {accent_rgba18}; border: 1px solid {accent_hex}; border-radius: 0px; }}
    QProgressBar {{ border: 1px solid {stroke}; border-radius: 0px; background: {bg2}; text-align: center; padding: 2px; }}
    QProgressBar::chunk {{ background: {accent_hex}; border-radius: 0px; margin: 1px; }}
    QAbstractItemView {{
      background: {bg2}; alternate-background-color: {bg3}; color: {text};
      selection-background-color: {accent_rgba24}; selection-color: {sel_text};
      border: 1px solid {stroke};
    }}
    QTableView {{ gridline-color: {stroke}; }}
    QTreeView::branch {{ background: transparent; }}
    QHeaderView::section {{
      background: {bg3}; color: {text_muted}; border: 1px solid {stroke};
      padding: 6px 8px; border-radius: 0px;
    }}
    QTableCornerButton::section {{ background: {bg3}; border: 1px solid {stroke}; }}
    QMenuBar {{ background: {bg}; color: {text}; }}
    QMenuBar::item {{ background: transparent; padding: 4px 8px; margin: 0 2px; border-radius: 0px; }}
    QMenuBar::item:selected {{ background: {bg2}; }}
    QMenu {{ background: {panel}; color: {text}; border: 1px solid {stroke2}; }}
    QMenu::separator {{ height: 1px; background: {stroke}; margin: 6px 8px; }}
    QMenu::item {{ padding: 6px 12px; }}
    QMenu::item:selected {{ background: {accent_rgba18}; color: {text}; }}
    QMenu::item:disabled {{ color: {text_muted}; }}
    QToolBar {{ background: {bg}; border-bottom: 1px solid {stroke}; spacing: 4px; }}
    QToolButton {{
      background: transparent; border: 1px solid {stroke}; border-radius: 0px; padding: 4px 6px; color: {icon_fg};
    }}
    QToolButton:hover {{ background: {bg2}; border-color: {stroke2}; color: {icon_fg_hover}; }}
    QToolButton:checked {{ background: {accent_rgba18}; border-color: {accent_hex}; color: {icon_fg_active}; }}
    QStatusBar {{ background: {bg}; color: {text_muted}; border-top: 1px solid {stroke}; }}
    QStatusBar QLabel {{ color: {text_muted}; }}
    QDockWidget::title {{ background: {bg2}; padding: 4px 8px; border: 1px solid {stroke}; border-radius: 0px; }}
    QGroupBox {{ background: {bg}; border: 1px solid {stroke}; border-radius: 0px; margin-top: 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {text_muted}; background: {bg}; }}
    QSplitter::handle {{ background: {bg2}; border: 1px solid {stroke}; }}
    QSplitter::handle:horizontal {{ width: 6px; }}
    QSplitter::handle:vertical   {{ height: 6px; }}
    QSplitter::handle:hover {{ background: {bg3}; border-color: {stroke2}; }}
    QCalendarWidget QWidget {{ alternate-background-color: {bg2}; }}
    QCalendarWidget QToolButton {{ background: {bg2}; border: 1px solid {stroke}; border-radius: 0px; padding: 4px 6px; color: {icon_fg}; }}
    QCalendarWidget QToolButton:hover {{ background: {bg3}; border-color: {stroke2}; color: {icon_fg_hover}; }}
    QCalendarWidget QAbstractItemView:enabled {{ selection-background-color: {accent_rgba24}; selection-color: {sel_text}; }}
    QDateTimeEdit::drop-down {{ border-left: 1px solid {stroke}; width: 24px; margin: 0; border-radius: 0px; }}
    QToolTip {{ background: {panel}; color: {text}; border: 1px solid {stroke2}; padding: 6px 8px; border-radius: 0px; }}
    QMessageBox {{ background: {bg}; }}
    QMessageBox QLabel {{ color: {text}; }}
    QMessageBox QPushButton {{ min-width: 72px; }}
    QDialogButtonBox QPushButton {{ padding: 6px 12px; border-radius: 0px; border: 1px solid {stroke}; background: {bg2}; }}
    QDialogButtonBox QPushButton:hover {{ border-color: {stroke2}; }}
    QDialogButtonBox QPushButton:default {{ background: {accent_hex}; color: {sel_text}; border-color: {accent_hex}; }}
    QFrame#SearchField {{ background: {bg2}; border: 1px solid {stroke}; border-radius: 0px; }}
    QFrame#SearchField QLineEdit {{ border: none; background: transparent; padding: 6px 8px; }}
    QFrame#SearchField QToolButton {{ border: none; background: transparent; padding: 6px; border-left: 1px solid {stroke}; color: {icon_fg}; }}
    QFrame#SearchField QToolButton:hover {{ background: {shadow_hint}; color: {icon_fg_hover}; }}
    QLabel[badge="free"] {{ color: {rgb_cyan}; border: 1px solid {stroke}; border-radius: 0px; padding: 2px 6px; background: {accent_rgba08}; }}
    QLabel[badge="top"]  {{ color: {rgb_blue}; border: 1px solid {stroke}; border-radius: 0px; padding: 2px 6px; }}
    QLabel[badge="new"]  {{ color: {rgb_pink}; border: 1px solid {stroke}; border-radius: 0px; padding: 2px 6px; }}
    *[density="compact"] QLineEdit,
    *[density="compact"] QComboBox,
    *[density="compact"] QTextEdit,
    *[density="compact"] QPlainTextEdit {{ padding: 4px 8px; }}
    *[density="roomy"] QLineEdit,
    *[density="roomy"] QComboBox,
    *[density="roomy"] QTextEdit,
    *[density="roomy"] QPlainTextEdit {{ padding: 10px 14px; }}
    QLineEdit:focus {{ border: 1px solid {accent_hex}; }}
    QComboBox:focus {{ border: 1px solid {accent_hex}; }}
    QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {accent_hex}; }}
    QListWidget::item, QListView::item {{ padding: 6px 8px; }}
    QListWidget::item:selected, QListView::item:selected {{ background: {accent_rgba24}; color: {sel_text}; }}
    QListWidget::item:hover:!selected, QListView::item:hover:!selected {{ background: {shadow_hint}; }}
    QTreeView::item {{ padding: 4px 6px; }}
    QTreeView::item:selected {{ background: {accent_rgba24}; color: {sel_text}; }}
    QTreeView::item:hover:!selected {{ background: {shadow_hint}; }}
    QTreeView::branch:has-siblings:!adjoins-item {{ border-image: none; }}
    QTreeView::branch:has-siblings:adjoins-item {{ border-image: none; }}
    QTableView {{ selection-background-color: {accent_rgba24}; selection-color: {sel_text}; alternate
    
    """
        return qss

# --- Sidebar icon resolve caches and aliases ---
_ICON_CACHE: Dict[str, QIcon] = {}
_ICON_MISS: Dict[str, bool] = {}
_ICON_ALIASES = {
    "bookmark.svg": "bookmarks.png",
    "bookmark.png": "bookmarks.png",
    "bookmarks.svg": "bookmarks.png",
    "history.svg": "history.png",
    "download.svg": "download.png",
    "settings.svg": "settings.png",
    "home.svg": "home.png",
    "profile.svg": "profile.png",
    "power.svg": "power.png",
    "restart.svg": "restart.png",
    "broom.svg": "broom.png",
    "trash.svg": "trash.png",
    "volume-on.svg": "volume-on.png",
    "volume-off.svg": "volume-off.png",
    "sun.svg": "sun.png",
    "moon.svg": "moon.png",
    "lock.svg": "lock.png",
    "colors.svg": "colors.png",
    "fonts.svg": "fonts.png",
    "zoom.png": "zoom.svg",
    "offline.png": "offline.svg",
    "offline.svg": "offline.png",
}
def _fallback_icon_pixmap(size: int = 20) -> QIcon:
    pm = QPixmap(size, size); pm.fill(Qt.transparent)
    painter = QPainter(pm); painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QPen(QColor(0,0,0,60), 1))
    painter.setBrush(QColor(127,127,127,60))
    r = pm.rect().adjusted(2,2,-2,-2)
    painter.drawRoundedRect(r, 4, 4)
    painter.end()
    return QIcon(pm)
