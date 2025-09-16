
# -*- coding: utf-8 -*-
"""
extensions_loader.py — загрузчик расширений для Salem Explorer (PyQt5)

Особенности
- Читает расширения из папки (manifest.json или авто-скан .js/.css)
- Ставит QWebEngineScript на профиль: document_start / document_end / document_idle
- Доинжектит CSS/JS после loadFinished (SPA/динамические роуты)
- Безопасная вставка CSS: ждём head/body, обновляем <style id="...">
- Совместимость: есть метод inject_into(webview) и alias load_all()
"""

from __future__ import annotations

import json
import os
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from PyQt5.QtCore import QObject
from PyQt5.QtWebEngineWidgets import QWebEngineProfile, QWebEngineScript, QWebEngineView


@dataclass
class Extension:
    name: str
    path: str
    enabled: bool = True
    # простой манифест
    js: List[str] = field(default_factory=list)
    css: List[str] = field(default_factory=list)
    run_at: str = "document_end"    # по умолчанию
    world: str = "application"      # main | application
    # chrome-like content_scripts
    content_scripts: List[dict] = field(default_factory=list)  # [{js, css, run_at, matches?}]


class ExtensionLoader(QObject):
    def __init__(self, extensions_dir: str, profile: Optional[QWebEngineProfile] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.extensions_dir = os.path.abspath(extensions_dir)
        self.profile = profile or QWebEngineProfile.defaultProfile()
        self._exts: Dict[str, Extension] = {}
        self._installed: Dict[str, List[QWebEngineScript]] = {}
        # сохранение статусов включения
        self.state_file = os.path.join(self.extensions_dir, "enabled_extensions.json")
        self.enabled_extensions = self._load_enabled_states()
        # грузим расширения
        self._load_all()

    # ------------------------------ Public API ------------------------------

    def install_profile_scripts(self) -> None:
        """Установить QWebEngineScript'ы на профиль (срабатывают до loadFinished)."""
        try:
            scripts = self.profile.scripts()
            # убрать прошлые наши скрипты
            for lst in self._installed.values():
                for s in lst:
                    try:
                        scripts.remove(s)
                    except Exception:
                        pass
            self._installed.clear()

            for ext in self._exts.values():
                if not ext.enabled:
                    continue
                built = self._build_scripts(ext)
                for s in built:
                    scripts.insert(s)
                self._installed[ext.name] = built

            print(f"[EXT] ✅ Profile scripts installed for: {', '.join(self._installed.keys())}")
        except Exception as e:
            print(f"[EXT] ❌ install_profile_scripts error: {e}")
            traceback.print_exc()

    def attach(self, webview: QWebEngineView) -> None:
        """Подключить runtime-инъекции к webview (полезно для CSS и SPA)."""
        if not isinstance(webview, QWebEngineView):
            return
        webview.loadFinished.connect(lambda ok, w=webview: self._inject_runtime(w))

    # Старое имя метода — на всякий случай
    def inject_into(self, webview: QWebEngineView) -> None:
        """Совместимость: разовая доинъекция CSS/JS в webview."""
        try:
            self._inject_runtime(webview)
        except Exception as e:
            print(f"[EXT] inject_into error: {e}")

    def enable(self, name: str, enabled: bool = True) -> None:
        ext = self._exts.get(name)
        if not ext:
            print(f"[EXT] ⚠ not found: {name}")
            return
        ext.enabled = bool(enabled)
        self.enabled_extensions[name] = ext.enabled
        self._save_enabled_states()

    def disable(self, name: str) -> None:
        self.enable(name, False)

    def list(self) -> List[Extension]:
        return list(self._exts.values())

    def reload(self) -> None:
        self._load_all()
        self.install_profile_scripts()

    def reload_extension(self, name: str) -> None:
        self.reload()

    # ------------------------------ Internal --------------------------------

    # alias для совместимости, если кто-то вызывает .load_all()
    def load_all(self) -> None:
        self._load_all()

    def _load_all(self) -> None:
        """Сканирует папку расширений и заполняет self._exts."""
        self._exts.clear()
        if not os.path.isdir(self.extensions_dir):
            print(f"[EXT] ⚠ extensions dir not found: {self.extensions_dir}")
            return
        for entry in sorted(os.listdir(self.extensions_dir)):
            path = os.path.join(self.extensions_dir, entry)
            if not os.path.isdir(path):
                continue
            ext = self._load_one(entry, path)
            if ext:
                # применим сохранённый статус включения
                saved = self.enabled_extensions.get(ext.name)
                if saved is not None:
                    ext.enabled = bool(saved)
                self._exts[ext.name] = ext
        print(f"[EXT] loaded: {len(self._exts)} extensions")

    def _load_one(self, entry: str, path: str) -> Optional[Extension]:
        mf_path = os.path.join(path, "manifest.json")
        try:
            if os.path.isfile(mf_path):
                with open(mf_path, "r", encoding="utf-8") as f:
                    mf = json.load(f)
                name = mf.get("name") or entry
                enabled = bool(mf.get("enabled", True))
                world = (mf.get("world") or "application").lower()
                run_at = (mf.get("run_at") or "document_end").lower()
                js = [os.path.join(path, p) for p in mf.get("js", []) if isinstance(p, str)]
                css = [os.path.join(path, p) for p in mf.get("css", []) if isinstance(p, str)]
                # content_scripts
                norm_cs = []
                for cs in mf.get("content_scripts", []) or []:
                    ncs = dict(cs)
                    ncs["js"] = [os.path.join(path, p) for p in ncs.get("js", []) if isinstance(p, str)]
                    ncs["css"] = [os.path.join(path, p) for p in ncs.get("css", []) if isinstance(p, str)]
                    ncs["run_at"] = (ncs.get("run_at") or "document_idle").lower()
                    norm_cs.append(ncs)
                return Extension(name=name, path=path, enabled=enabled, js=js, css=css,
                                 run_at=run_at, world=world, content_scripts=norm_cs)
            else:
                # простой авто-скан
                js, css = [], []
                for fn in sorted(os.listdir(path)):
                    fp = os.path.join(path, fn)
                    if fn.lower().endswith(".js"):
                        js.append(fp)
                    elif fn.lower().endswith(".css"):
                        css.append(fp)
                return Extension(name=entry, path=path, js=js, css=css)
        except Exception as e:
            print(f"[EXT] ❌ load error {entry}: {e}")
            traceback.print_exc()
            return None

    # ------------------------------ Builders --------------------------------

    def _build_scripts(self, ext: Extension) -> List[QWebEngineScript]:
        built: List[QWebEngineScript] = []
        when_map = {
            "document_start": QWebEngineScript.DocumentCreation,
            "document_end": QWebEngineScript.DocumentReady,
            "document_idle": QWebEngineScript.Deferred,
        }
        world_map = {
            "main": QWebEngineScript.MainWorld,
            "application": QWebEngineScript.ApplicationWorld,
        }

        def make_script(name: str, code: str, when: str, world: str) -> QWebEngineScript:
            s = QWebEngineScript()
            s.setName(name)
            s.setInjectionPoint(when_map.get(when, QWebEngineScript.DocumentReady))
            s.setWorldId(world_map.get(world, QWebEngineScript.ApplicationWorld))
            s.setRunsOnSubFrames(True)
            s.setSourceCode(code)
            return s

        # простой манифест: объединяем CSS в один <style>, JS — по отдельности
        if ext.css:
            css_code = "\n".join(self._read_text(p) for p in ext.css)
            js_code = self._style_injector_js(css_code, style_id=f"ext-style-{ext.name}")
            built.append(make_script(f"ext-css::{ext.name}", js_code, ext.run_at, ext.world))
        for jp in ext.js:
            code = self._read_text(jp)
            built.append(make_script(f"ext-js::{ext.name}::{os.path.basename(jp)}", code, ext.run_at, ext.world))

        # content_scripts
        for i, cs in enumerate(ext.content_scripts):
            when = cs.get("run_at", "document_idle")
            js_list = cs.get("js", []) or []
            css_list = cs.get("css", []) or []
            if css_list:
                css_code = "\n".join(self._read_text(p) for p in css_list)
                built.append(make_script(f"ext-css::{ext.name}::{i}", self._style_injector_js(css_code, f"ext-style-{ext.name}-{i}"), when, ext.world))
            for jp in js_list:
                code = self._read_text(jp)
                built.append(make_script(f"ext-js::{ext.name}::{i}::{os.path.basename(jp)}", code, when, ext.world))

        return built

    # ------------------------------ Runtime ---------------------------------

    def _inject_runtime(self, webview: QWebEngineView) -> None:
        """После загрузки страницы: обновляем CSS и выполняем JS ещё раз (если нужно)."""
        try:
            for ext in self._exts.values():
                if not ext.enabled:
                    continue
                # простой манифест
                for cssp in ext.css:
                    self._inject_css_file(webview, cssp, style_id=f"ext-style-{ext.name}")
                for jsp in ext.js:
                    self._inject_js_file(webview, jsp)
                # content_scripts
                for i, cs in enumerate(ext.content_scripts):
                    for cssp in cs.get("css", []) or []:
                        self._inject_css_file(webview, cssp, style_id=f"ext-style-{ext.name}-{i}")
                    for jsp in cs.get("js", []) or []:
                        self._inject_js_file(webview, jsp)
        except Exception as e:
            print(f"[EXT] ❌ runtime inject: {e}")
            traceback.print_exc()

    # ------------------------------ Injectors --------------------------------

    def _inject_js_file(self, webview: QWebEngineView, path: str) -> None:
        code = self._read_text(path)
        if not code:
            return
        try:
            webview.page().runJavaScript(code)
        except Exception as e:
            print(f"[EXT] ❌ JS inject error: {path} — {e}")

    def _inject_css_file(self, webview: QWebEngineView, path: str, style_id: Optional[str] = None) -> None:
        css = self._read_text(path)
        if not css:
            return
        self._inject_css_text(webview, css, style_id or f"ext-style-{os.path.basename(path)}")

    def _inject_css_text(self, webview: QWebEngineView, css_text: str, style_id: Optional[str] = None) -> None:
        """Надёжная инъекция CSS: ждём появления head/body и только потом вставляем <style id=...>."""
        try:
            sid = style_id or f"ext-style-{abs(hash(css_text)) % 100000}"
            safe = css_text.translate(str.maketrans({ "\\": "\\\\", "`": "\\`" }))
            js = (
                "(function(){"
                "try{"
                f"var id='{sid}';"
                "var css=`" + safe + "`;"
                "var d=document;"
                "function put(){"
                "  var root = d.head || d.documentElement || d.body;"
                "  if(!root) return false;"
                "  var old = d.getElementById(id);"
                "  if(old && old.tagName && old.tagName.toLowerCase()==='style'){ old.textContent = css; return true; }"
                "  var s = d.createElement('style'); s.id=id; s.type='text/css';"
                "  s.appendChild(d.createTextNode(css));"
                "  root.appendChild(s);"
                "  return true;"
                "}"
                "if(!put()){"
                "  var tries=0;"
                "  (function tick(){"
                "    tries++;"
                "    if(put() || tries>60) return;"
                "    setTimeout(tick, 50);"
                "  })();"
                "}"
                "}catch(e){ console.error('[EXT] css inject', e);}"
                "})();"
            )
            webview.page().runJavaScript(js)
        except Exception as e:
            print(f"[EXT] ❌ CSS inject(text) error: {e}")

    # ------------------------------ Utils -----------------------------------

    def _read_text(self, path: str, encoding: str = "utf-8") -> str:
        try:
            with open(path, "r", encoding=encoding, errors="ignore") as f:
                return f.read()
        except Exception as e:
            print(f"[EXT] ⚠ read error {path}: {e}")
            return ""

    def _style_injector_js(self, css_text: str, style_id: str) -> str:
        safe = css_text.translate(str.maketrans({ "\\": "\\\\", "`": "\\`" }))
        return (
            "(function(){"
            "try{"
            f"var id='{style_id}';"
            "var css=`" + safe + "`;"
            "var d=document;"
            "function put(){"
            "  var root = d.head || d.documentElement || d.body;"
            "  if(!root) return false;"
            "  var old = d.getElementById(id);"
            "  if(old && old.tagName && old.tagName.toLowerCase()==='style'){ old.textContent = css; return true; }"
            "  var s = d.createElement('style'); s.id=id; s.type='text/css';"
            "  s.appendChild(d.createTextNode(css));"
            "  root.appendChild(s);"
            "  return true;"
            "}"
            "if(!put()){"
            "  var tries=0;"
            "  (function tick(){"
            "    tries++;"
            "    if(put() || tries>60) return;"
            "    setTimeout(tick, 50);"
            "  })();"
            "}"
            "}catch(e){ console.error('[EXT] css inject', e);}"
            "})();"
        )

    # -------------- state persistence --------------

    def _load_enabled_states(self) -> dict:
        try:
            if os.path.isfile(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): bool(v) for k, v in data.items()}
        except Exception:
            pass
        return {}

    def _save_enabled_states(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.enabled_extensions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("[EXT] ⚠ state save failed:", e)
