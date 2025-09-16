# launcher_plugins/loader.py
import os, sys, json, importlib, traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

class Plugin:
    def __init__(self, name, path, manifest):
        self.name = name
        self.path = path
        self.manifest = manifest

def discover_plugins(dir_path):
    plugins = []
    if not os.path.isdir(dir_path): return plugins
    for entry in os.listdir(dir_path):
        pdir = os.path.join(dir_path, entry)
        if not os.path.isdir(pdir): continue
        manifest = {"name": entry, "priority": 100, "modules": [], "stage": "background"}
        mpath = os.path.join(pdir, "manifest.json")
        if os.path.exists(mpath):
            try:
                with open(mpath, "r", encoding="utf-8") as f:
                    manifest.update(json.load(f))
            except Exception:
                traceback.print_exc()
        plugins.append(Plugin(entry, pdir, manifest))
    # сортируем по приоритету (меньше — раньше)
    plugins.sort(key=lambda x: int(x.manifest.get("priority", 100)))
    return plugins

def _import_module(mod):
    try:
        return importlib.import_module(mod), None
    except Exception as e:
        return None, (mod, e)

def preload_modules_concurrently(modules, max_workers=4):
    errs = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futs = {ex.submit(_import_module, m): m for m in modules}
        for fut in as_completed(futs):
            _, err = fut.result()
            if err: errs.append(err)
    return errs

def warmup_disk(paths):
    # просто читаем файлы в память — ОС кладёт в page cache
    for p in paths:
        try:
            with open(p, "rb") as f:
                f.read(131072)  # первые 128К достаточно, чтобы “разбудить” файл
        except Exception:
            pass
