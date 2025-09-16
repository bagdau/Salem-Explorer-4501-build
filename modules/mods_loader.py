# modules/mods_loader.py
# -*- coding: utf-8 -*-
import os, json, zipfile, re, shutil, uuid
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable

from PyQt5.QtCore import QObject, QUrl, pyqtSlot, pyqtSignal, QVariant
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineScript
from PyQt5.QtWebChannel import QWebChannel


@dataclass
class Mod:
    root: str
    manifest: Dict
    enabled: bool = False

    @property
    def id(self) -> str:
        return self.manifest.get("id") or os.path.basename(self.root)

    @property
    def name(self) -> str:
        return self.manifest.get("name") or self.id

    @property
    def version(self) -> str:
        return self.manifest.get("version") or "0.0.0"

    @property
    def description(self) -> str:
        return self.manifest.get("description") or ""

    @property
    def icon_path(self) -> Optional[str]:
        p = self.manifest.get("icon")
        if not p: return None
        ap = os.path.join(self.root, p)
        return ap if os.path.exists(ap) else None

    @property
    def matches(self) -> List[str]:
        return list(self.manifest.get("matches", []))

    @property
    def excludes(self) -> List[str]:
        return list(self.manifest.get("exclude_matches", []))

    @property
    def css_files(self) -> List[str]:
        return [os.path.join(self.root, p) for p in self.manifest.get("content_css", [])]

    @property
    def js_files(self) -> List[str]:
        return [os.path.join(self.root, p) for p in self.manifest.get("content_js", [])]


# ──────────────────────────────────────────────────────────────────────
#   ModsBridge: JS ↔ Python через QWebChannel
#   На стороне страницы доступно: window.salem.call(name, payload)
#   Ивенты из Python: bridge.notify(name, payload) -> JS: window.salem.on(name, fn)
# ──────────────────────────────────────────────────────────────────────
class ModsBridge(QObject):
    notifySignal = pyqtSignal(str, dict)  # -> JS

    def __init__(self, owner_loader: "ModLoader"):
        super().__init__()
        self._owner = owner_loader
        self._custom_handler: Optional[Callable[[str, dict], dict]] = None

    def set_handler(self, handler: Optional[Callable[[str, dict], dict]]):
        self._custom_handler = handler

    @pyqtSlot(str, "QVariant", result="QVariant")
    def call(self, name: str, payload: QVariant):
        try:
            data = payload if isinstance(payload, dict) else {}
            # Базовые методы
            if name == "ping":
                return {"ok": True, "version": "1.0"}
            if name == "getSetting":
                k = data.get("key")
                return {"ok": True, "value": self._owner._settings_get(k)}
            if name == "setSetting":
                k, v = data.get("key"), data.get("value")
                self._owner._settings_set(k, v)
                return {"ok": True}

            # Кастомный обработчик (подключает внешние сервисы браузера)
            if self._custom_handler:
                out = self._custom_handler(name, data) or {}
                out.setdefault("ok", True)
                return out
            return {"ok": False, "error": "no_handler"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # Python -> JS
    def notify(self, event_name: str, payload: dict):
        try:
            self.notifySignal.emit(event_name, payload or {})
        except Exception:
            pass


class ModLoader(QObject):
    """
    Лоадер модов:
      • mods_dir — папка с модами
      • enabled_mods.json — вкл/выкл
      • load_order.json — порядок загрузки (список id сверху вниз)
      • install_zip(path), install_dir(path)
      • enable/disable/remove/move
      • attach(webview) — авто-инъекции по matches/excludes
      • inject_mod_into_view(webview, mod) — ручная инъекция (для превью)
      • JS API: window.salem.call(name, payload) / window.salem.on(name, fn)
    """
    def __init__(self, mods_dir: str, state_file: Optional[str] = None, profile=None, parent=None):
        super().__init__(parent)
        self.mods_dir = os.path.abspath(mods_dir)
        os.makedirs(self.mods_dir, exist_ok=True)
        self.state_file = state_file or os.path.join(self.mods_dir, "enabled_mods.json")
        self.order_file = os.path.join(self.mods_dir, "load_order.json")
        self.settings_file = os.path.join(self.mods_dir, "mod_settings.json")
        self.profile = profile

        self._mods: Dict[str, Mod] = {}
        self._enabled_ids: Dict[str, bool] = {}
        self._load_order: List[str] = []
        self._bridge_per_view: Dict[int, ModsBridge] = {}
        self._api_handler: Optional[Callable[[str, dict], dict]] = None

        self.reload()

    # ── API handler для интеграции с сервисами браузера ───────────────
    def set_api_handler(self, handler: Optional[Callable[[str, dict], dict]]):
        """Позволяет браузеру навесить обработчик запросов от модов."""
        self._api_handler = handler
        # Прокинем всем уже созданным мостам
        for br in self._bridge_per_view.values():
            br.set_handler(handler)

    # ── публичное API ─────────────────────────────────────────────────
    def reload(self):
        self._enabled_ids = self._load_states()
        self._load_order = self._load_order_load()
        self._mods = {}
        for name in sorted(os.listdir(self.mods_dir)):
            root = os.path.join(self.mods_dir, name)
            if not os.path.isdir(root): 
                continue
            manifest = self._read_manifest(root)
            if not manifest: 
                continue
            m = Mod(root=root, manifest=manifest, enabled=bool(self._enabled_ids.get(manifest.get("id") or name)))
            self._mods[m.id] = m

        # нормализуем порядок
        known = list(self._mods.keys())
        order = [i for i in self._load_order if i in known]
        order += [i for i in known if i not in order]
        self._load_order = order
        self._load_order_save()

    def list_mods(self) -> List[Mod]:
        # возвращаем в порядке загрузки
        return [self._mods[i] for i in self._load_order if i in self._mods]

    def get(self, mod_id: str) -> Optional[Mod]:
        return self._mods.get(mod_id)

    # — включение/выключение —
    def enable(self, mod_id: str, enabled: bool = True):
        if mod_id in self._mods:
            self._mods[mod_id].enabled = bool(enabled)
            self._enabled_ids[mod_id] = bool(enabled)
            self._save_states()

    def disable(self, mod_id: str):
        self.enable(mod_id, False)

    # — удаление —
    def remove(self, mod_id: str):
        m = self._mods.get(mod_id)
        if not m: return
        try:
            shutil.rmtree(m.root, ignore_errors=True)
        finally:
            self._mods.pop(mod_id, None)
            self._enabled_ids.pop(mod_id, None)
            self._load_order = [i for i in self._load_order if i != mod_id]
            self._save_states(); self._load_order_save()

    def open_dir(self) -> str:
        return self.mods_dir

    # — порядок —
    def order(self) -> List[str]:
        return list(self._load_order)

    def set_order(self, new_ids: List[str]):
        known = set(self._mods.keys())
        self._load_order = [i for i in new_ids if i in known]
        for i in self._mods.keys():
            if i not in self._load_order:
                self._load_order.append(i)
        self._load_order_save()

    def move(self, mod_id: str, delta: int):
        if mod_id not in self._load_order:
            return
        i = self._load_order.index(mod_id)
        j = max(0, min(len(self._load_order)-1, i + delta))
        if i == j: return
        self._load_order[i], self._load_order[j] = self._load_order[j], self._load_order[i]
        self._load_order_save()

    # — установка —
    def install_zip(self, zip_path: str) -> Optional[Mod]:
        if not (zip_path and os.path.exists(zip_path) and zip_path.lower().endswith(".zip")):
            return None
        tmp_root = os.path.join(self.mods_dir, f"__tmp_{uuid.uuid4().hex[:8]}")
        os.makedirs(tmp_root, exist_ok=True)
        try:
            with zipfile.ZipFile(zip_path, 'r') as z:
                z.extractall(tmp_root)
            mod_root = self._find_manifest_root(tmp_root)
            manifest = self._read_manifest(mod_root)
            if not manifest:
                raise RuntimeError("В ZIP не найден валидный mod.json")
            return self._finalize_install(manifest, mod_root, tmp_root)
        except Exception:
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise

    def install_dir(self, folder_path: str) -> Optional[Mod]:
        """Импорт из папки."""
        if not (folder_path and os.path.isdir(folder_path)):
            return None
        manifest = self._read_manifest(folder_path)
        if not manifest:
            raise RuntimeError("В папке нет mod.json")
        # Копируем в каталог модов
        tmp_root = os.path.join(self.mods_dir, f"__tmp_{uuid.uuid4().hex[:8]}")
        shutil.copytree(folder_path, tmp_root)
        try:
            return self._finalize_install(manifest, tmp_root, None)
        except Exception:
            shutil.rmtree(tmp_root, ignore_errors=True)
            raise

    def _finalize_install(self, manifest: Dict, mod_root: str, tmp_root_to_remove: Optional[str]):
        mod_id = manifest.get("id") or os.path.basename(mod_root)
        safe_name = self._sanitize(mod_id)
        final_root = os.path.join(self.mods_dir, safe_name)
        if os.path.exists(final_root):
            shutil.rmtree(final_root, ignore_errors=True)
        shutil.move(mod_root, final_root)
        if tmp_root_to_remove:
            shutil.rmtree(tmp_root_to_remove, ignore_errors=True)

        m = Mod(root=final_root, manifest=manifest, enabled=True)
        self._mods[m.id] = m
        self._enabled_ids[m.id] = True
        # поместим новый мод в конец (или куда скажешь — можно и в начало)
        if m.id in self._load_order:
            self._load_order.remove(m.id)
        self._load_order.append(m.id)
        self._save_states(); self._load_order_save()
        return m

    # — привязка к вкладке —
    def attach(self, webview: QWebEngineView):
        """Подключаем: 1) авто-инъекции; 2) JS-мост window.salem (QWebChannel)."""
        if not webview or hasattr(webview, "_mods_attached"):
            return
        webview._mods_attached = True

        # JS-мост (один на страницу)
        channel = QWebChannel(webview.page())
        bridge = ModsBridge(self)
        bridge.set_handler(self._api_handler)
        channel.registerObject("SalemMods", bridge)
        webview.page().setWebChannel(channel)
        self._bridge_per_view[id(webview)] = bridge

        # Инициализация window.salem (подгружаем qwebchannel.js из ресурсов Qt)
        init_js = r"""
        (function(){
          if (window.salem && window.salem.__ready) return;
          function ready(fn){ document.readyState!='loading' ? fn() : document.addEventListener('DOMContentLoaded',fn); }
          function boot(){
            var s=document.createElement('script');
            s.src='qrc:///qtwebchannel/qwebchannel.js';
            s.onload=function(){
              new QWebChannel(qt.webChannelTransport, function(channel){
                const bridge = channel.objects.SalemMods;
                const listeners = {};
                window.salem = {
                  __ready: true,
                  call: function(name, payload){ return bridge.call(name, payload||{}); },
                  on: function(ev, fn){ (listeners[ev]||(listeners[ev]=[])).push(fn); }
                };
                bridge.notifySignal.connect(function(ev, data){
                  (listeners[ev]||[]).forEach(function(fn){ try{ fn(data||{}); }catch(e){} });
                });
              });
            };
            document.documentElement.appendChild(s);
          }
          ready(boot);
        })();
        """
        sc = QWebEngineScript()
        sc.setName("salem-mods-bridge")
        sc.setInjectionPoint(QWebEngineScript.DocumentCreation)
        sc.setWorldId(QWebEngineScript.MainWorld)
        sc.setRunsOnSubFrames(True)
        sc.setSourceCode(init_js)
        webview.page().scripts().insert(sc)

        # Авто-инъекция по URL
        def _inject_for_url():
            try:
                url = webview.url().toString()
                self._inject_into_view(webview, url)
            except Exception as e:
                print("[mods] inject error:", e)

        try:
            webview.loadFinished.connect(lambda ok: ok and _inject_for_url())
            webview.urlChanged.connect(lambda _u: _inject_for_url())
        except Exception:
            pass

    # — программная инъекция конкретного мода (для превью) —
    def inject_mod_into_view(self, webview: QWebEngineView, mod: Mod):
        self._inject_mod_assets(webview, mod)

    # ── инъекции ─────────────────────────────────────────────────────
    def _inject_into_view(self, webview: QWebEngineView, url: str):
        if not url or "http" not in url:
            return
        # моды строго по порядку
        for mod in self.list_mods():
            if not mod.enabled: 
                continue
            if not self._url_ok(url, mod.matches, mod.excludes):
                continue
            self._inject_mod_assets(webview, mod)

    def _inject_mod_assets(self, webview: QWebEngineView, mod: Mod):
        # CSS
        for css in mod.css_files:
            try:
                css_text = self._read_file(css)
            except Exception:
                css_text = ""
            if css_text:
                esc = css_text.replace("\\", "\\\\").replace("`", "\\`")
                js = ((
                    "(()=>{try{var s=document.createElement('style');"
                    f"s.dataset.salemMod='{mod.id}';"
                    f"s.textContent=`{esc}`;document.documentElement.appendChild(s);}}catch(e){{}}}})();"
                ))
                try: webview.page().runJavaScript(js)
                except Exception: pass
        # JS
        for jsf in mod.js_files:
            try:
                js_code = self._read_file(jsf)
            except Exception:
                js_code = ""
            if js_code:
                try: webview.page().runJavaScript(js_code)
                except Exception: pass

    # ── settings storage для API ─────────────────────────────────────
    def _settings_get(self, key: Optional[str]):
        try:
            if not key: return None
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get(key)
        except Exception:
            pass
        return None

    def _settings_set(self, key: Optional[str], value):
        if not key: return
        data = {}
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
        except Exception:
            data = {}
        data[key] = value
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── утилиты ──────────────────────────────────────────────────────
    def _load_states(self) -> Dict[str, bool]:
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {str(k): bool(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_states(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._enabled_ids, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[mods] save states failed:", e)

    def _load_order_load(self) -> List[str]:
        try:
            if os.path.exists(self.order_file):
                with open(self.order_file, "r", encoding="utf-8") as f:
                    arr = json.load(f)
                    if isinstance(arr, list):
                        return [str(x) for x in arr]
        except Exception:
            pass
        return []

    def _load_order_save(self):
        try:
            with open(self.order_file, "w", encoding="utf-8") as f:
                json.dump(self._load_order, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _find_manifest_root(self, base: str) -> str:
        cand = os.path.join(base, "mod.json")
        if os.path.exists(cand):
            return base
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "mod.json")):
                return p
        return base

    def _read_manifest(self, root: str) -> Optional[Dict]:
        try:
            with open(os.path.join(root, "mod.json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    @staticmethod
    def _read_file(path: str) -> str:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _sanitize(s: str) -> str:
        return re.sub(r"[^a-zA-Z0-9._-]+", "_", s).strip("_") or "mod_" + uuid.uuid4().hex[:6]

    @staticmethod
    def _wild_to_regex(pat: str):
        import re as _re
        pat = _re.escape(pat).replace(r"\*", ".*").replace(r"\?", ".")
        return _re.compile("^" + pat + "$", _re.IGNORECASE)

    def _url_ok(self, url: str, matches: List[str], excludes: List[str]) -> bool:
        if excludes:
            for ex in excludes:
                if self._wild_to_regex(ex).match(url):
                    return False
        if not matches:
            return True
        for m in matches:
            if self._wild_to_regex(m).match(url):
                return True
        return False
