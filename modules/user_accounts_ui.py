# modules/user_account_ui.py
import os, json
from urllib.parse import urlparse

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFormLayout, QCheckBox, QGroupBox
)

# Простое локальное хранилище (позже можно зашифровать)
PASSWORDS_PATH = os.path.join(
    os.getenv("APPDATA", os.path.expanduser("~")),
    "SalemBrowser", "passwords.json"
)

def _ensure_storage():
    folder = os.path.dirname(PASSWORDS_PATH)
    if not os.path.isdir(folder):
        os.makedirs(folder, exist_ok=True)
    if not os.path.isfile(PASSWORDS_PATH):
        with open(PASSWORDS_PATH, "w", encoding="utf-8") as f:
            json.dump({"autofill_enabled": True, "items": []}, f, ensure_ascii=False, indent=2)

def _load_storage():
    _ensure_storage()
    with open(PASSWORDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_storage(data):
    _ensure_storage()
    with open(PASSWORDS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _domain_from(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

class UserAccountPanel(QWidget):
    """
    Отдельная вкладка-окно «Аккаунт»:
      • Профиль: ручной ввод логина/пароля, считывание со страницы, заполнение на страницу, сохранение на домен
      • Сохранённые: список записей по доменам, быстрое автозаполнение/удаление
      • Настройки: вкл/выкл автозаполнения, очистка базы
    """
    def __init__(self, parent_browser):
        super().__init__()
        self.browser = parent_browser      # ссылка на SalemBrowser
        self.current_webview = None        # активный QWebEngineView
        self.state = _load_storage()

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_profile_tab(), "Профиль")
        self.tabs.addTab(self._build_passwords_tab(), "Сохранённые")
        self.tabs.addTab(self._build_settings_tab(), "Настройки")

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    # === публичное API для браузера ===
    def set_current_webview(self, webview):
        self.current_webview = webview

    def try_autofill_on_load(self, webview):
        """Дёргать после loadFinished: заполняет, если запись для домена найдена и автозаполнение включено."""
        st = _load_storage()
        if not st.get("autofill_enabled", True):
            return
        url = webview.url().toString()
        dom = _domain_from(url)
        for it in st.get("items", []):
            if it.get("domain") == dom:
                self.set_current_webview(webview)
                self._inject_fill(it.get("username",""), it.get("password",""))
                break

    # === вкладки ===
    def _build_profile_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        self.le_login = QLineEdit()
        self.le_pass  = QLineEdit()
        self.le_pass.setEchoMode(QLineEdit.Password)

        btns = QHBoxLayout()
        btn_detect = QPushButton("Считать со страницы")
        btn_apply  = QPushButton("Заполнить на странице")
        btn_save   = QPushButton("Сохранить для домена")
        btns.addWidget(btn_detect)
        btns.addWidget(btn_apply)
        btns.addWidget(btn_save)

        form.addRow(QLabel("Логин/Email:"), self.le_login)
        form.addRow(QLabel("Пароль:"), self.le_pass)
        form.addRow(btns)

        btn_detect.clicked.connect(self._detect_from_page)
        btn_apply.clicked.connect(self._apply_to_page)
        btn_save.clicked.connect(self._save_for_domain)

        return w

    def _build_passwords_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        self.list_view = QListWidget()
        self._reload_passwords_list()

        row = QHBoxLayout()
        btn_fill = QPushButton("Заполнить выбранное")
        btn_del  = QPushButton("Удалить выбранное")
        row.addWidget(btn_fill); row.addWidget(btn_del)

        v.addWidget(self.list_view)
        v.addLayout(row)

        btn_fill.clicked.connect(self._fill_selected)
        btn_del.clicked.connect(self._delete_selected)

        return w

    def _build_settings_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)

        box = QGroupBox("Автозаполнение")
        b  = QVBoxLayout(box)
        self.cb_autofill = QCheckBox("Включить автозаполнение на сайтах")
        self.cb_autofill.setChecked(bool(self.state.get("autofill_enabled", True)))
        b.addWidget(self.cb_autofill)

        btn_clear = QPushButton("Очистить все сохранённые пароли")

        v.addWidget(box)
        v.addWidget(btn_clear)
        v.addStretch(1)

        self.cb_autofill.stateChanged.connect(self._toggle_autofill)
        btn_clear.clicked.connect(self._clear_all)

        return w

    # === внутренние операции ===
    def _reload_passwords_list(self):
        self.list_view.clear()
        self.state = _load_storage()
        for item in self.state.get("items", []):
            dom = item.get("domain","")
            user = item.get("username","")
            li = QListWidgetItem(f"{dom} — {user}")
            li.setData(Qt.UserRole, item)
            self.list_view.addItem(li)

    def _toggle_autofill(self, _):
        data = _load_storage()
        data["autofill_enabled"] = bool(self.cb_autofill.isChecked())
        _save_storage(data)

    def _clear_all(self):
        if QMessageBox.question(self, "Подтвердите", "Удалить все сохранённые пароли?") == QMessageBox.Yes:
            _save_storage({"autofill_enabled": True, "items": []})
            self._reload_passwords_list()

    def _delete_selected(self):
        it = self.list_view.currentItem()
        if not it: return
        rec = it.data(Qt.UserRole)
        dom = rec.get("domain")
        data = _load_storage()
        data["items"] = [i for i in data.get("items", []) if i.get("domain") != dom]
        _save_storage(data)
        self._reload_passwords_list()

    def _fill_selected(self):
        it = self.list_view.currentItem()
        if not it or not self.current_webview: return
        rec = it.data(Qt.UserRole)
        self._inject_fill(rec.get("username",""), rec.get("password",""))

    def _save_for_domain(self):
        if not self.current_webview:
            QMessageBox.warning(self, "Аккаунт", "Нет активной вкладки.")
            return
        url = self.current_webview.url().toString()
        dom = _domain_from(url)
        if not dom:
            QMessageBox.warning(self, "Аккаунт", "Не удалось определить домен текущей страницы.")
            return

        username = self.le_login.text().strip()
        password = self.le_pass.text()
        if not username or not password:
            QMessageBox.warning(self, "Аккаунт", "Введите логин и пароль перед сохранением.")
            return

        data = _load_storage()
        items = [i for i in data.get("items", []) if i.get("domain") != dom]
        items.append({"domain": dom, "username": username, "password": password})
        data["items"] = items
        _save_storage(data)
        self._reload_passwords_list()
        QMessageBox.information(self, "Аккаунт", f"Данные сохранены для {dom}")

    # === JS-интеграция со страницей ===
    def _detect_from_page(self):
        if not self.current_webview:
            return
        js = r"""
        (function(){
          function q(sel){return document.querySelector(sel);}
          let usr = q('input[type=email],input[name*=user],input[name*=login],input[type=text]');
          let pwd = q('input[type=password]');
          return JSON.stringify({
            username: (usr && usr.value) ? usr.value : "",
            password: (pwd && pwd.value) ? pwd.value : ""
          });
        })();
        """
        self.current_webview.page().runJavaScript(js, self._on_detect)

    def _on_detect(self, result):
        try:
            obj = json.loads(result) if result else {}
        except Exception:
            obj = {}
        self.le_login.setText(obj.get("username",""))
        self.le_pass.setText(obj.get("password",""))

    def _apply_to_page(self):
        self._inject_fill(self.le_login.text().strip(), self.le_pass.text())

    def _inject_fill(self, username: str, password: str):
        if not self.current_webview:
            return
        import json as _json
        username_js = _json.dumps(username)
        password_js = _json.dumps(password)
        js = f"""
        (function(){{
          function pickUser(){{
            let cands = Array.from(document.querySelectorAll('input'));
            let u = cands.find(i => /email/i.test(i.type));
            if(!u) u = cands.find(i => /user|login|name/i.test(i.name||""));
            if(!u) u = cands.find(i => i.type==='text');
            return u;
          }}
          let u = pickUser();
          let p = document.querySelector('input[type=password]');
          if(u) {{ u.focus(); u.value = {username_js}; u.dispatchEvent(new Event('input', {{bubbles:true}})); }}
          if(p) {{ p.focus(); p.value = {password_js}; p.dispatchEvent(new Event('input', {{bubbles:true}})); }}
          return !!(u||p);
        }})();
        """
        self.current_webview.page().runJavaScript(js, lambda ok: None)
