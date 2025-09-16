# -*- coding: utf-8 -*-
"""
preload_core: быстрый разогрев QtWebEngine перед показом UI.
НИКАКИХ Qt-объектов здесь не создаём — только импорты/файловый прогрев.
"""

import os, sys, glob, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

def log(msg, level="INFO"):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]} [{level}] {msg}", flush=True)

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

def warmup_disk(paths, limit=250):
    if limit > 0:
        paths = paths[:limit]
    for p in paths:
        try:
            with open(p, "rb") as f:
                f.read(131072)  # 128KB: хватает, чтобы ОС положила в page cache
        except Exception:
            pass

def run(manifest):
    try:
        log("[preload_core] start")
        mods = manifest.get("modules", [])
        warm = manifest.get("warmup", {}) or {}
        limit = int(warm.get("limit", 250))

        # 1) Подогреем Qt DLL/PYD/PAK/DAT — это ускоряет первый импорт WebEngine
        if warm.get("qt_files", True):
            try:
                import PyQt5  # noqa
                qt_dir = os.path.dirname(PyQt5.__file__)
                patterns = ("**/*.dll", "**/*.pyd", "**/*.pak", "**/*.dat", "**/icudtl.dat")
                candidates = []
                for pat in patterns:
                    candidates.extend(glob.glob(os.path.join(qt_dir, pat), recursive=True))
                warmup_disk(candidates, limit=limit)
                log(f"[preload_core] warmed ~{min(len(candidates), limit)} Qt files")
            except Exception:
                traceback.print_exc()

        # 2) Параллельные импорты тяжёлых модулей
        errs = preload_modules_concurrently(mods, max_workers=4)
        for mod_name, e in errs:
            log(f"[preload_core] import error: {mod_name}: {e}", level="WARN")

        log("[preload_core] ready")
    except Exception:
        traceback.print_exc()
        log("[preload_core] failed", level="ERROR")
