# -*- coding: utf-8 -*-
"""
preload_media: фоновый прогрев статических файлов и параллельный импорт,
плюс безблокирующий запуск MediaHub (порт 7000) и news_proxy (порт 5000).

ВАЖНО: не создаём Qt-объекты. Никаких app.run() — только WSGI (make_server).
Совместимо с Flask 2/3 и любыми экспортами: .wsgi, create_app(), app.wsgi_app,
а также классами SalemMediaServer/SalemServer.
"""

import os, glob, threading, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

def log(msg, level="INFO"):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} [{level}] {msg}", flush=True)

# --- параллельные импорты ------------------------------------------------------
def _import_module(mod):
    try:
        import importlib
        importlib.invalidate_caches()
        importlib.import_module(mod)
        return None
    except Exception as e:
        return (mod, e)

def preload_modules_concurrently(modules, max_workers=4):
    errs = []
    if not modules:
        return errs
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = [ex.submit(_import_module, m) for m in modules]
        for fut in as_completed(futs):
            err = fut.result()
            if err:
                errs.append(err)
    return errs

# --- прогрев диска -------------------------------------------------------------
def warmup_disk(paths, limit=300):
    if limit > 0:
        paths = paths[:limit]
    for p in paths:
        try:
            with open(p, "rb") as f:
                f.read(131072)  # 128KB — достаточно для page cache
        except Exception:
            pass

# --- тихий WSGI без флуда по /health ------------------------------------------
from werkzeug.serving import make_server, WSGIRequestHandler

class QuietHealthHandler(WSGIRequestHandler):
    def log(self, type, message, *args):
        if " /health " in message:
            return
        super().log(type, message, *args)

def _start_wsgi(wsgi_app, host, port, name):
    def _runner():
        try:
            httpd = make_server(host, port, wsgi_app, request_handler=QuietHealthHandler)
            log(f"[preload_media] {name} WSGI on {host}:{port}")
            httpd.serve_forever()
        except Exception:
            traceback.print_exc()
    t = threading.Thread(target=_runner, name=f"{name}-wsgi", daemon=True)
    t.start()
    return t

# --- извлечение WSGI из чего угодно -------------------------------------------
def _extract_wsgi_from_module(mod):
    """
    Возвращает (wsgi_callable, friendly_name) либо (None, None), поддерживая:
    - классы SalemMediaServer/SalemServer со свойством .wsgi
    - атрибут 'wsgi' (callable)
    - create_app() -> Flask app -> app.wsgi_app
    - app (Flask) -> app.wsgi_app
    """
    try:
        # 1) Классы-обёртки нашего проекта
        for cls_name in ("SalemMediaServer", "SalemServer"):
            if hasattr(mod, cls_name):
                srv_cls = getattr(mod, cls_name)
                try:
                    srv = srv_cls()
                    if hasattr(srv, "wsgi"):
                        return srv.wsgi, cls_name
                except Exception:
                    traceback.print_exc()

        # 2) Прямой WSGI
        if hasattr(mod, "wsgi"):
            wsgi = getattr(mod, "wsgi")
            if callable(wsgi):
                return wsgi, "wsgi"

        # 3) Фабрика Flask
        if hasattr(mod, "create_app"):
            app = mod.create_app()
            if hasattr(app, "wsgi_app"):
                return app.wsgi_app, "create_app().wsgi_app"

        # 4) Flask app
        if hasattr(mod, "app"):
            app = getattr(mod, "app")
            # Защита от путаницы с модулем flask.app
            if hasattr(app, "wsgi_app"):
                return app.wsgi_app, "app.wsgi_app"
    except Exception:
        traceback.print_exc()

    return None, None

def _start_server_from_module(mod_name, cfg, fallback_name):
    try:
        mod = __import__(mod_name, fromlist=['*'])
    except Exception:
        log(f"[preload_media] import failed: {mod_name}", level="WARN")
        traceback.print_exc()
        return None

    wsgi, kind = _extract_wsgi_from_module(mod)
    if wsgi is None:
        log(f"[preload_media] no WSGI in {mod_name}", level="WARN")
        return None

    host = str(cfg.get("host", "127.0.0.1"))
    default_port = 7000 if "mediahub" in fallback_name else 5000
    port = int(cfg.get("port", default_port))
    log(f"[preload_media] starting {fallback_name} ({kind}) on {host}:{port}")
    return _start_wsgi(wsgi, host, port, fallback_name)

# --- точка входа плагина -------------------------------------------------------
def run(manifest):
    try:
        log("[preload_media] start")

        # 1) Прогреть статику
        warm_conf = manifest.get("warmup", {}) or {}
        warm_paths = warm_conf.get("paths", [])
        limit = int(warm_conf.get("limit", 300))
        candidates = []
        for base in warm_paths:
            if not os.path.isdir(base):
                continue
            for pat in ("**/*.dll", "**/*.pyd", "**/*.pak", "**/*.dat",
                        "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.webp",
                        "**/*.svg", "**/*.js", "**/*.css", "**/*.json", "**/*.html"):
                candidates.extend(glob.glob(os.path.join(base, pat), recursive=True))
        warmup_disk(candidates, limit=limit)
        log(f"[preload_media] warmed ~{min(len(candidates), limit)} files")

        # 2) Параллельные импорты тяжёлых модулей
        mods = manifest.get("modules", [])
        errs = preload_modules_concurrently(mods, max_workers=4)
        for mod_name, e in errs:
            log(f"[preload_media] import error: {mod_name}: {e}", level="WARN")

        # 3) Поднимаем локальные серверы через WSGI, если включено
        if manifest.get("start_servers", True):
            _start_server_from_module("MediaHub.mediahub_server", manifest.get("mediahub", {}), "mediahub")
            _start_server_from_module("news_proxy.server",     manifest.get("news_proxy", {}), "news_proxy")

        log("[preload_media] ready")
    except Exception:
        traceback.print_exc()
        log("[preload_media] failed", level="ERROR")
