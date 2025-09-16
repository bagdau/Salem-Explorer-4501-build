# extensions_popup.py — мини-менеджер расширений с popup/options и стабильным WebExtensions-shim
from __future__ import annotations
import os, json, traceback, urllib.parse, urllib.request
from typing import Dict, Any, Optional, List, Callable

from PyQt5.QtCore import (
    Qt, QPoint, QPropertyAnimation, QEasingCurve, QRect, QUrl, QObject, QEvent
)
from PyQt5.QtGui import QIcon, QColor, QPalette
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QFrame, QMessageBox, QLineEdit, QToolButton, QStackedLayout,
    QGraphicsDropShadowEffect, QApplication
)
from PyQt5.QtWebEngineWidgets import (
    QWebEngineView, QWebEnginePage, QWebEngineScript, QWebEngineSettings
)

# -------------------- utils --------------------

def _read_manifest(ext_dir: str) -> Optional[Dict[str, Any]]:
    for name in ("manifest.json", "extension.json"):
        p = os.path.join(ext_dir, name)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                traceback.print_exc(); return None
    return None

def _default_popup_url(m: Dict[str, Any], d: str) -> Optional[str]:
    try:
        if isinstance(m, dict):
            ba = m.get("browser_action") or m.get("action") or {}
            if isinstance(ba, dict) and ba.get("default_popup"):
                return str(ba["default_popup"]).lstrip("/\\")
            if m.get("popup"):
                return str(m["popup"]).lstrip("/\\")
        for fn in ("popup.html", "popup.htm"):
            if os.path.isfile(os.path.join(d, fn)):
                return fn
    except Exception:
        pass
    return None

def _default_dashboard_url(m: Dict[str, Any], d: str) -> Optional[str]:
    try:
        if isinstance(m, dict):
            if m.get("options_page"):
                return str(m["options_page"]).lstrip("/\\")
            opt = m.get("options_ui")
            if isinstance(opt, dict) and opt.get("page"):
                return str(opt["page"]).lstrip("/\\")
        for fn in ("dashboard.html", "index.html", "options.html"):
            if os.path.isfile(os.path.join(d, fn)):
                return fn
    except Exception:
        pass
    return None

def _has_popup(m: Dict[str, Any], d: str) -> bool: return _default_popup_url(m, d) is not None

def _has_dash(m: Dict[str, Any], d: str) -> bool:  return _default_dashboard_url(m, d) is not None

def _safe_makedirs(p: str) -> None:
    try: os.makedirs(p, exist_ok=True)
    except Exception: pass

def _save_states_atomic(path: str, data: Dict[str, bool]) -> None:
    d = os.path.dirname(path) or "."; _safe_makedirs(d)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.replace(tmp, path) if os.path.exists(path) else os.rename(tmp, path)
    except Exception:
        with open(path, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def _favicon_for_url(url: str, cache_dir: str, size: int = 24) -> QIcon:
    try:
        domain = urllib.parse.urlparse(url).netloc or ""
        if not domain: return QIcon()
        _safe_makedirs(cache_dir)
        cache = os.path.join(cache_dir, domain.replace(":", "_") + f"_{size}.png")
        if os.path.isfile(cache): return QIcon(cache)
        api = f"https://www.google.com/s2/favicons?domain={urllib.parse.quote(domain)}&sz={size}"
        with urllib.request.urlopen(api, timeout=5) as r: data = r.read()
        with open(cache, "wb") as f: f.write(data)
        return QIcon(cache)
    except Exception:
        return QIcon()

# -------------------- web engine helpers --------------------

class _MiniPage(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):
        try: print(f"[Popup JS] {message} ({source}:{line})")
        except Exception: pass

# глобальный щит: клик вне карточки → закрыть (если не закреплён)
class _OutsideClickFilter(QObject):
    def __init__(self, host: 'ExtensionsMiniPopup'): super().__init__(host); self.host = host
    def eventFilter(self, obj: QObject, ev: QEvent) -> bool:
        if self.host._pinned: return False
        if ev.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.TouchBegin):
            try: gp = ev.globalPos()
            except Exception: return False
            try:
                r = self.host._card.geometry(); tl = self.host.mapToGlobal(r.topLeft()); gr = QRect(tl, r.size())
                if not gr.contains(gp): self.host.close(); return True
            except Exception: return False
        return False

# -------------------- main dialog --------------------

class ExtensionsMiniPopup(QDialog):
    """Popup менеджер расширений с превью popup/options и WebExtensions-shim."""
    def __init__(self, parent: QWidget, extension_loader, open_full_callback):
        super().__init__(parent, flags=Qt.FramelessWindowHint | Qt.Tool)
        self.setObjectName("ExtMiniPopup")
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._pinned = False; self._closing = False
        self.extension_loader = extension_loader
        self.open_full_callback = open_full_callback
        self.extensions_dir = getattr(extension_loader, "extensions_dir", "extensions")
        self.state_file = getattr(extension_loader, "state_file", "enabled_extensions.json")
        self.enabled_states = dict(getattr(extension_loader, "enabled_extensions", {}))

        base_cache = os.path.join(os.path.expanduser("~"), ".salem_cache")
        self._fav_cache_dir = os.path.join(base_cache, "favicons"); _safe_makedirs(self._fav_cache_dir)

        # Card container
        self._card = QFrame(self); self._card.setObjectName("popupCard"); self._card.setAttribute(Qt.WA_StyledBackground, True)
        shadow = QGraphicsDropShadowEffect(self._card); shadow.setBlurRadius(24); shadow.setColor(QColor(0,0,0,160)); shadow.setOffset(0,7)
        self._card.setGraphicsEffect(shadow)

        card_box = QVBoxLayout(self._card); card_box.setContentsMargins(10,10,10,10); card_box.setSpacing(0)

        # Stacked pages
        self._stack = QStackedLayout(); card_box.addLayout(self._stack)
        self._page_list = QWidget(self._card); self._page_preview = QWidget(self._card)
        self._stack.addWidget(self._page_list); self._stack.addWidget(self._page_preview)

        self._build_list_page(); self._build_preview_page()

        self.setMinimumSize(540, 400); self.resize(540, 420)
        self._apply_dark_theme(); self.reload_list()

        self._outside_filter = _OutsideClickFilter(self)
        QApplication.instance().installEventFilter(self._outside_filter)

    # sizing
    def resizeEvent(self, e): self._card.setGeometry(self.rect()); super().resizeEvent(e)

        # ----- animations / open_at -----
    def open_at(self, anchor: QWidget):
        """Открывает мини-менеджер около anchor с плавной анимацией."""
        self._stack.setCurrentWidget(self._page_list)
        self.reload_list()
        self.adjustSize()

        g = anchor.mapToGlobal(QPoint(anchor.width()//2, anchor.height()))
        final_w = max(self.width(), 520)
        final_h = max(self.height(), 400)
        x = g.x() - final_w + anchor.width()
        y = g.y() + 6

        screen = anchor.screen().availableGeometry()
        x = max(screen.left()+8, min(x, screen.right()-final_w-8))
        y = max(screen.top()+8,  min(y, screen.bottom()-final_h-8))

        final_rect = QRect(x, y, final_w, final_h)
        start_rect = QRect(x, y-12, final_w, final_h)

        self.setWindowOpacity(0.0)
        self.setGeometry(start_rect)
        self.show()

        a1 = QPropertyAnimation(self, b"windowOpacity", self)
        a1.setDuration(170)
        a1.setStartValue(0.0)
        a1.setEndValue(1.0)
        a1.setEasingCurve(QEasingCurve.OutCubic)

        a2 = QPropertyAnimation(self, b"geometry", self)
        a2.setDuration(170)
        a2.setStartValue(start_rect)
        a2.setEndValue(final_rect)
        a2.setEasingCurve(QEasingCurve.OutCubic)

        a1.start()
        a2.start()


    # ----- theme (dark only) -----
    def _apply_dark_theme(self):
        pal = self.palette(); pal.setColor(QPalette.Window, QColor("#0f141b")); pal.setColor(QPalette.Base, QColor("#0f141b")); pal.setColor(QPalette.Text, QColor("#e6e9ee"))
        self.setPalette(pal); self._card.setPalette(pal)
        self.setStyleSheet(self._qss_dark())
        if hasattr(self, "web") and self.web:
            try:
                self.web.setAttribute(Qt.WA_StyledBackground, True)
                self.web.setStyleSheet("background:#0f141b;")
                self.web.page().setBackgroundColor(QColor("#0f141b"))
            except Exception: pass
        self.style().unpolish(self); self.style().polish(self); self.update()

    def _qss_dark(self) -> str:
        return """
        #ExtMiniPopup { background: transparent; }
        #popupCard { background: rgba(16,20,28,0.92); border: 1px solid #263242; border-radius:14px; }
        QWidget { color:#e6e9ee; font: 10pt "Segoe UI"; }
        QPushButton#chip, QPushButton#chipWarn, QPushButton#pinBtn { min-height:32px; padding:0 12px; border-radius:10px; border:1px solid #2b3a4e; background:#1a2332; color:#d4dbe5; }
        QPushButton#chip:hover { background:#223046; }
        QPushButton#chipWarn { border-color:#3b2230; background:#2a1b24; color:#ffd6e5; }
        QPushButton#chipWarn:hover { background:#3a2531; }
        QPushButton#pinBtn:checked { background:#3fa9f5; border-color:#3fa9f5; color:#0f141b; }
        QLabel#miniTitle { font-weight:800; font-size:12pt; color:#79a5ff; }
        QLabel#miniBadge { min-height:32px; padding:0 10px; margin-left:6px; color:#fff; background:#2c3e56; border-radius:9px; font: 9pt "Segoe UI Semibold"; }
        QLineEdit#miniSearch { min-height:32px; padding:0 12px; background:#111827; color:#e6e9ee; border:1px solid #2b3a4e; border-radius:10px; }
        QLineEdit#miniSearch:focus { border-color:#07fff3; background:#152034; }
        QScrollArea { border:none; background:transparent; }
        QScrollArea > QWidget#qt_scrollarea_viewport { background: transparent; }
        QAbstractScrollArea { background:transparent; }
        QScrollBar:vertical { background:transparent; width:10px; margin:4px 0 4px 0; }
        QScrollBar::handle:vertical { background:#2b3a4e; border-radius:5px; min-height:24px; }
        QScrollBar::handle:vertical:hover { background:#375172; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
        QScrollBar:horizontal { height:0; }
        QFrame#ExtMiniRow { background:#0f141b; border:1px solid #1f2a3a; border-radius:12px; }
        QLabel#extTitleMini { font-weight:700; }
        QLabel#extVerChip { padding:2px 6px; color:#a7b8cf; background:#1b2636; border:1px solid #253246; border-radius:6px; margin-left:6px; font: 8.5pt "Segoe UI"; }
        QLabel#extDescMini { color:#a8b2c5; }
        QToolButton#pillBtn { min-height:32px; padding:0 12px; border-radius:9px; background:#1a2332; border:1px solid #2b3a4e; color:#d4dbe5; }
        QToolButton#pillBtn:hover { background:#223046; }
        QToolButton#iconBtn { min-height:32px; border-radius:8px; padding:0 8px; background:#0f141b; border:1px solid #1f2a3a; color:#c7d2e3; }
        QToolButton#iconBtn:hover { background:#1a2332; }
        QPushButton#switchMini { min-width:48px; max-width:48px; min-height:28px; border-radius:14px; border:1px solid #2b3a4e; background:#243145; color:transparent; }
        QPushButton#switchMini:checked { background:#3fa9f5; border-color:#3fa9f5; }
        QWidget#pvHeader { background:#0f141b; border:1px solid #1f2a3a; border-radius:10px; }
        QLineEdit#addr { min-height:32px; padding:0 10px; background:#0c121a; border:1px solid #1f2a3a; border-radius:8px; color:#e6e9ee; }
        QLineEdit#addr:focus { border-color:#3fa9f5; }
        QWebEngineView { background: transparent; }
        """

    # ----- list page -----
    def _build_list_page(self):
        root = QVBoxLayout(self._page_list); root.setContentsMargins(10,10,10,10); root.setSpacing(10)
        header = QHBoxLayout(); header.setContentsMargins(0,0,0,0); header.setSpacing(8)
        self.lbl_title = QLabel("Кеңейтулер"); self.lbl_title.setObjectName("miniTitle")
        self.lbl_count = QLabel("0/0"); self.lbl_count.setObjectName("miniBadge")
        self.ed_search = QLineEdit(); self.ed_search.setPlaceholderText("Іздеу / Поиск…")
        self.ed_search.setObjectName("miniSearch"); self.ed_search.textChanged.connect(self._on_search)
        self.btn_pin = QPushButton("📌"); self.btn_pin.setObjectName("pinBtn"); self.btn_pin.setCheckable(True)
        self.btn_pin.setToolTip("Не закрывать при клике вне окна"); self.btn_pin.toggled.connect(lambda v: setattr(self, "_pinned", bool(v)))
        self.btn_all_on  = QPushButton("Все вкл");  self.btn_all_on.setObjectName("chip"); self.btn_all_on.clicked.connect(lambda: self._toggle_all(True))
        self.btn_all_off = QPushButton("Все выкл"); self.btn_all_off.setObjectName("chipWarn"); self.btn_all_off.clicked.connect(lambda: self._toggle_all(False))
        btn_full = QPushButton("мен"); btn_full.setObjectName("chip"); btn_full.clicked.connect(self._open_full); btn_full.setToolTip("Полный менеджер…")
        header.addWidget(self.lbl_title); header.addWidget(self.lbl_count); header.addStretch(1)
        header.addWidget(self.ed_search); header.addWidget(self.btn_pin)
        header.addWidget(self.btn_all_on); header.addWidget(self.btn_all_off); header.addWidget(btn_full)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.list_widget = QWidget(); self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(0, 0, 0, 0); self.list_layout.setSpacing(10); self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        root.addLayout(header); root.addWidget(self.scroll)
        self._empty_label = QLabel("Пока нет расширений.\nПоложи их в папку /extensions и обнови.")
        self._empty_label.setAlignment(Qt.AlignCenter); self._empty_label.setStyleSheet("color:#9aa6b9; padding:24px;")
        self.list_layout.insertWidget(self.list_layout.count()-1, self._empty_label); self._empty_label.hide()
        self._rows: List[QFrame] = []

    # ----- preview page -----
    def _build_preview_page(self):
        root = QVBoxLayout(self._page_preview); root.setContentsMargins(10,10,10,10); root.setSpacing(8)
        head = QWidget(self._page_preview); head.setObjectName("pvHeader")
        h = QHBoxLayout(head); h.setContentsMargins(8,8,8,8); h.setSpacing(6)
        self.btn_pv_back = QToolButton(head); self.btn_pv_back.setText("⟵"); self.btn_pv_back.setObjectName("iconBtn")
        self.btn_nav_back = QToolButton(head); self.btn_nav_back.setText("◁"); self.btn_nav_back.setObjectName("iconBtn")
        self.btn_nav_fwd  = QToolButton(head); self.btn_nav_fwd.setText("▷"); self.btn_nav_fwd.setObjectName("iconBtn")
        self.btn_nav_reload = QToolButton(head); self.btn_nav_reload.setText("⟳"); self.btn_nav_reload.setObjectName("iconBtn")
        self.btn_pv_back.clicked.connect(self._back_to_list)
        self.btn_nav_back.clicked.connect(lambda: self.web and self.web.back())
        self.btn_nav_fwd.clicked.connect(lambda: self.web and self.web.forward())
        self.btn_nav_reload.clicked.connect(lambda: self.web and self.web.reload())
        self.addr = QLineEdit(head); self.addr.setObjectName("addr"); self.addr.setPlaceholderText("Адрес…"); self.addr.returnPressed.connect(self._nav_from_addr)
        open_full = QPushButton("Открыть в менеджере…", head); open_full.setObjectName("chip"); open_full.clicked.connect(self._open_full)
        h.addWidget(self.btn_pv_back); h.addWidget(self.btn_nav_back); h.addWidget(self.btn_nav_fwd); h.addWidget(self.btn_nav_reload); h.addWidget(self.addr, 1); h.addWidget(open_full)
        self.web = QWebEngineView(self._page_preview); self.web.setPage(_MiniPage(self.web))
        # настройки, важные для локального контента
        try:
            s = self.web.settings()
            for attr in (
                QWebEngineSettings.JavascriptEnabled,
                QWebEngineSettings.LocalStorageEnabled,
                QWebEngineSettings.PluginsEnabled,
                QWebEngineSettings.WebGLEnabled,
                QWebEngineSettings.LocalContentCanAccessFileUrls,
                QWebEngineSettings.LocalContentCanAccessRemoteUrls,
                QWebEngineSettings.ErrorPageEnabled,
            ):
                s.setAttribute(attr, True)
        except Exception: pass
        # фон web
        self.web.setAttribute(Qt.WA_StyledBackground, True); self.web.setStyleSheet("background:#0f141b;")
        try: self.web.page().setBackgroundColor(QColor("#0f141b"))
        except Exception: pass
        # глобальная установка shim на профиль + страховка runJavaScript
        self._install_webext_shim_globally()
        try:
            self.web.page().loadStarted.connect(lambda: self._inject_shim_via_runjs())
            self.web.page().loadStarted.connect(lambda: print("[MiniPopup] loadStarted:", self.web.url().toString()))
            self.web.page().loadFinished.connect(lambda ok: print("[MiniPopup] loadFinished:", ok, self.web.url().toString()))
        except Exception: pass
        root.addWidget(head); root.addWidget(self.web, 1)
        self.web.urlChanged.connect(lambda u: self.addr.setText(u.toString()))

    # ----- SHIM install -----
    def _shim_js(self) -> str:
        # базируется на document.baseURI — работает для любых file:// страниц расширений
        return r"""
        (function(){
          try{ if (window.__salemWebExtShimInstalled) return; }catch(e){}
          try{ Object.defineProperty(window,'__salemWebExtShimInstalled',{value:true,configurable:false}); }catch(e){ window.__salemWebExtShimInstalled=true; }
          const base = document.baseURI || location.href;
          const toURL = (p)=>{ try{ return new URL(p||'', base).toString(); }catch(e){ return base; } };
          const promisifyCb = (fn)=>function(){ var args=[...arguments]; var cb=(typeof args[args.length-1]==='function')?args.pop():null; var r=Promise.resolve().then(()=>fn.apply(null,args)); if(cb) r.then(v=>cb(v)); return r; };
          const tabs = {
            query: promisifyCb((q)=>[{ id:1, active:true, url:location.href, title:document.title }]),
            sendMessage: promisifyCb(()=>true),
            update: promisifyCb(()=>true)
          };
          const KEY='__salem_ext_storage__';
          const load=()=>{ try{ return JSON.parse(localStorage.getItem(KEY)||'{}'); }catch(e){ return {}; } };
          const save=(o)=>localStorage.setItem(KEY, JSON.stringify(o));
          const storage={ local:{
            get: promisifyCb((k)=>{ const d=load(); if(!k) return d; if(Array.isArray(k)){const o={};k.forEach(x=>o[x]=d[x]);return o} if(typeof k==='string') return {[k]:d[k]}; if(typeof k==='object'){const o={};Object.keys(k).forEach(x=>o[x]=(x in d)?d[x]:k[x]);return o} return d; }),
            set: promisifyCb((o)=>{ const d=load(); Object.assign(d,o||{}); save(d); }),
            remove: promisifyCb((k)=>{ const d=load(); (Array.isArray(k)?k:[k]).forEach(x=>delete d[x]); save(d); }),
            clear: promisifyCb(()=>save({}))
          }}; storage.sync = storage.local;
          const listeners=[];
          const runtime={ id:'salem-mini-host', getURL:(p)=>toURL(p), getManifest:()=>({ manifest_version:2, name:document.title, version:'0.0.0' }),
            sendMessage: promisifyCb((msg)=>null),
            onMessage:{ addListener:(fn)=>{ if(typeof fn==='function') listeners.push(fn); }, removeListener:(fn)=>{ const i=listeners.indexOf(fn); if(i>=0) listeners.splice(i,1); } },
            connect: ()=>({ onMessage:{addListener:()=>{}}, postMessage:()=>{}, disconnect:()=>{} })
          };
          const i18n={ getMessage:(k)=>k };
          const api={ tabs, storage, runtime, i18n };
          try{ Object.defineProperty(window,'chrome',{ value:api, writable:false, configurable:false }); }catch(e){ window.chrome=api; }
          if(!window.browser) window.browser=api;
          window.addEventListener('salem:message',(ev)=>{ try{ listeners.forEach(fn=>fn(ev.detail,null,()=>{})); }catch(e){} });
          try{ console.log('[Shim] installed'); }catch(e){}
        })();
        """

    def _install_webext_shim_globally(self):
        try:
            js = self._shim_js()
            # 1) На профиль (раньше и стабильнее)
            prof = self.web.page().profile()
            for point in (QWebEngineScript.DocumentCreation, QWebEngineScript.DocumentReady):
                sc = QWebEngineScript(); sc.setName(f"salem-webext-shim-{int(point)}"); sc.setInjectionPoint(point)
                sc.setWorldId(QWebEngineScript.MainWorld); sc.setRunsOnSubFrames(True); sc.setSourceCode(js)
                prof.scripts().insert(sc)
        except Exception:
            traceback.print_exc()

    def _inject_shim_via_runjs(self):
        # Дополнительная страховка: прокидываем shim ранним runJavaScript
        try:
            self.web.page().runJavaScript(self._shim_js())
        except Exception:
            pass

    # ----- list operations -----
    def _clear_rows(self):
        for w in getattr(self, "_rows", []):
            try: w.setParent(None); w.deleteLater()
            except Exception: pass
        self._rows = []

    def reload_list(self):
        from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QToolButton
        class _Row(QFrame):
            def __init__(self, parent: QWidget, name: str, path: str, manifest: Dict[str, Any], enabled: bool, callbacks: Dict[str, Callable], fav_cache: str):
                super().__init__(parent)
                self.ext_name, self.ext_path, self.manifest, self.enabled, self.cbs = name, path, (manifest or {}), bool(enabled), callbacks
                self.setObjectName("ExtMiniRow"); self.setFrameShape(QFrame.NoFrame)
                title = self.manifest.get("name") or name
                ver   = self.manifest.get("version") or ""
                desc  = (self.manifest.get("description") or "—").strip()
                home  = self.manifest.get("homepage_url") or ""
                icon = _favicon_for_url(home, fav_cache, 24)
                icon_lbl = QLabel(); icon_lbl.setObjectName("extFavicon"); icon_lbl.setPixmap(icon.pixmap(18, 18))
                lbl_title = QLabel(title); lbl_title.setObjectName("extTitleMini")
                lbl_ver = QLabel(f"v{ver}") if ver else QLabel(""); lbl_ver.setObjectName("extVerChip")
                lbl_desc = QLabel(desc); lbl_desc.setObjectName("extDescMini"); lbl_desc.setWordWrap(True); lbl_desc.setMaximumHeight(44); lbl_desc.setToolTip(desc)
                btn_switch = QPushButton(""); btn_switch.setObjectName("switchMini"); btn_switch.setCheckable(True); btn_switch.setChecked(bool(enabled))
                btn_switch.clicked.connect(lambda ch: self.cbs.get("toggle", lambda *_: None)(self.ext_name, ch))
                btn_popup = QToolButton(self); btn_popup.setText("Popup"); btn_popup.setObjectName("pillBtn"); btn_popup.setEnabled(_has_popup(self.manifest, self.ext_path))
                btn_popup.clicked.connect(lambda: self.cbs.get("popup", lambda *_: None)(self.ext_name))
                btn_dash = QToolButton(self); btn_dash.setText("Панель"); btn_dash.setObjectName("pillBtn"); btn_dash.setEnabled(_has_dash(self.manifest, self.ext_path))
                btn_dash.clicked.connect(lambda: self.cbs.get("dashboard", lambda *_: None)(self.ext_name))
                btn_more = QToolButton(self); btn_more.setText("⋮"); btn_more.setObjectName("iconBtn"); btn_more.setToolTip("Ещё"); btn_more.setFixedWidth(32); btn_more.clicked.connect(self.cbs.get("open_full", lambda: None))
                top = QHBoxLayout(); top.setContentsMargins(0,0,0,0); top.setSpacing(8)
                top.addWidget(icon_lbl); top.addWidget(lbl_title); top.addWidget(lbl_ver); top.addStretch(1); top.addWidget(btn_switch)
                actions = QHBoxLayout(); actions.setContentsMargins(0,0,0,0); actions.setSpacing(8)
                actions.addWidget(btn_popup); actions.addWidget(btn_dash); actions.addStretch(1); actions.addWidget(btn_more)
                lay = QVBoxLayout(self); lay.setContentsMargins(12, 12, 12, 12); lay.setSpacing(8)
                lay.addLayout(top); lay.addWidget(lbl_desc); lay.addLayout(actions)
            def matches(self, needle: str) -> bool:
                n = (needle or "").strip().lower()
                if not n: return True
                hay = " ".join([self.manifest.get("name",""), self.manifest.get("description",""), self.ext_name]).lower()
                return n in hay
        self._clear_rows(); total = 0
        try:
            if os.path.isdir(self.extensions_dir):
                for name in sorted(os.listdir(self.extensions_dir), key=str.lower):
                    path = os.path.join(self.extensions_dir, name)
                    if not os.path.isdir(path): continue
                    man = _read_manifest(path)
                    if not man: continue
                    enabled = bool(self.enabled_states.get(name, False))
                    row = _Row(self.list_widget, name, path, man, enabled,
                               callbacks=dict(toggle=self._toggle_ext, popup=self._open_popup_inline,
                                              dashboard=self._open_dashboard_inline, open_full=self._open_full),
                               fav_cache=self._fav_cache_dir)
                    self._rows.append(row); self.list_layout.insertWidget(self.list_layout.count()-1, row); total += 1
        except Exception: traceback.print_exc()
        try: self._empty_label.setVisible(total == 0)
        except RuntimeError:
            self._empty_label = QLabel("Пока нет расширений."); self._empty_label.setAlignment(Qt.AlignCenter)
            self._empty_label.setStyleSheet("color:#9aa6b9; padding:24px;")
            self.list_layout.insertWidget(self.list_layout.count()-1, self._empty_label)
            self._empty_label.setVisible(total == 0)
        self._update_counter(); self._on_search(self.ed_search.text())

    def _update_counter(self):
        total = len(self._rows); visible = sum(1 for r in self._rows if r.isVisible()); self.lbl_count.setText(f"{visible}/{total}")

    # ----- list actions -----
    def _toggle_all(self, to_state: bool):
        changed = False
        for r in self._rows:
            if getattr(r, 'enabled', to_state) != to_state:
                try:
                    btn = r.findChild(QPushButton, "switchMini")
                    if btn: btn.blockSignals(True); btn.setChecked(to_state); btn.blockSignals(False)
                except Exception: pass
                changed = True
        if not changed: self._update_counter(); return
        for name in [getattr(r, 'ext_name', '') for r in self._rows]:
            if not name: continue
            self.enabled_states[name] = to_state
            try:
                if isinstance(self.extension_loader.enabled_extensions, dict):
                    self.extension_loader.enabled_extensions[name] = to_state
            except Exception: pass
        try: _save_states_atomic(self.state_file, self.enabled_states)
        except Exception as e: QMessageBox.critical(self, "JSON қатесі", f"Сақтау мүмкін емес:\n{e}")
        try:
            if hasattr(self.extension_loader, "reload"): self.extension_loader.reload()
        except Exception: pass
        self.reload_list()

    def _toggle_ext(self, name: str, enabled: bool):
        self.enabled_states[name] = bool(enabled)
        try:
            if isinstance(self.extension_loader.enabled_extensions, dict):
                self.extension_loader.enabled_extensions[name] = bool(enabled)
        except Exception: pass
        try: _save_states_atomic(self.state_file, self.enabled_states)
        except Exception as e: QMessageBox.critical(self, "JSON қатесі", f"Сақтау мүмкін емес:\n{e}")
        try:
            if hasattr(self.extension_loader, "reload"): self.extension_loader.reload()
        except Exception: pass

    def _on_search(self, text: str):
        t = (text or "").strip(); any_v = False
        for r in self._rows:
            v = r.matches(t); r.setVisible(v); any_v = any_v or v
        self._empty_label.setVisible(len(self._rows)==0 and not any_v)
        self._update_counter()

    # ----- open popup / dashboard -----
    def _open_popup_inline(self, name: str): self._open_inline(name, "popup")
    def _open_dashboard_inline(self, name: str): self._open_inline(name, "dashboard")

    def _open_inline(self, name: str, kind: str):
        try:
            path = os.path.join(self.extensions_dir, name)
            man = _read_manifest(path) or {}
            if kind == "popup":
                rel = _default_popup_url(man, path); none_text = "У этого расширения нет popup."
            else:
                rel = _default_dashboard_url(man, path); none_text = "У этого расширения нет панели (options/dashboard)."
            if not rel:
                QMessageBox.information(self, "Info", none_text); return
            if rel.startswith(("http://", "https://")):
                url = QUrl(rel)
            else:
                rel = rel.lstrip("/\\")
                url = QUrl.fromLocalFile(os.path.join(path, rel))
            # перед навигацией shim уже стоит глобально, плюс страховка runjs при loadStarted
            self.web.setUrl(url); self.addr.setText(url.toString()); self._stack.setCurrentWidget(self._page_preview)
        except Exception as e:
            traceback.print_exc(); QMessageBox.warning(self, "Error", f"Не удалось открыть: {e}")

    # ----- address nav -----
    def _back_to_list(self): self._stack.setCurrentWidget(self._page_list)
    def _nav_from_addr(self):
        t = (self.addr.text() or "").strip();
        if not t: return
        if "://" not in t:
            t = t.lstrip("/\\"); base = self.web.url()
            if base.isValid(): self.web.setUrl(base.resolved(QUrl(t))); return
            lf = QUrl.fromLocalFile(t); self.web.setUrl(lf if os.path.exists(t) else QUrl(f"http://{t}"))
        else:
            self.web.setUrl(QUrl(t))

    # ----- open full manager -----
    def _open_full(self):
        self.close(); cb = self.open_full_callback
        if callable(cb): cb()
