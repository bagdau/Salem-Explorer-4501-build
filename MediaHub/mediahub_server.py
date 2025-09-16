# mediahub_server.py
# -*- coding: utf-8 -*-
import os
import io
import json
import uuid
import time
import shutil
import mimetypes
from datetime import datetime
from typing import List, Dict, Any, Optional

from flask import (
    Flask, app, request, jsonify, send_from_directory, send_file, Response, make_response
    )

class SalemMediaServer:
    """
    ЕДИНСТВЕННЫЙ класс медиасервера (порт 7000) под SalemMedia UI.

    Уже было:
      GET  /            → SalemMedia.html
      GET  /ui          → SalemMedia.html (алиас)
      GET  /health      → {"ok": true}
      GET  /api/files   → список из index.json (+ простые фильтры)
      POST /api/upload  → загрузка FormData('files')
      GET  /media/<p>   → отдача файла, поддержка HTTP Range (перемотка)

    Добавлено:
      OPTIONS /api/*            → 204 для всех preflight
      POST    /api/meta         → {stored, name?, tags?} правка метаданных
      POST    /api/rename       → {stored, new_name} переименование файла на диске
      POST    /api/delete       → {stored} удалить файл и запись индекса
      POST    /api/clear        → {wipe:bool} очистить индекс; wipe=True — удалить файлы
      POST    /api/rescan       → перескан медиа-каталога, бережно мержит index
      GET     /api/stats        → суммарная статистика (по типам, объём, кол-во)
      GET     /api/file/<stored>→ мета по одному файлу (или 404)

    Все ответы — JSON; индекс сохраняется как {"files":[...]}.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 7000, root_dir: Optional[str] = None):
        self.host = host
        self.port = port
        self.ROOT = os.path.abspath(root_dir or os.path.dirname(__file__))
        self.MEDIA_DIR = os.path.join(self.ROOT, "media")
        self.INDEX_PATH = os.path.join(self.MEDIA_DIR, "index.json")
        os.makedirs(self.MEDIA_DIR, exist_ok=True)
        mimetypes.init()
        self.app = Flask(__name__)
        self._configure_routes()

    # ------------------- helpers -------------------

    @staticmethod
    def _now_iso() -> str:
        return datetime.fromtimestamp(time.time()).isoformat(timespec="seconds")

    @staticmethod
    def _safe_name(name: str) -> str:
        # Сохраняем расширение; чистим опасные символы
        name = (name or "file").replace("\\", "_").replace("/", "_")
        table = str.maketrans({c: "_" for c in '<>:"|?*'})
        name = name.translate(table).strip()
        return name or "file"

    @staticmethod
    def _kind_by_ext(filename: str) -> str:
        ext = (os.path.splitext(filename)[1] or "").lower().lstrip(".")
        if ext in ("mp3", "wav", "flac", "ogg", "m4a", "aac"): return "audio"
        if ext in ("mp4", "webm", "mkv", "avi", "mov", "m4v"): return "video"
        if ext in ("jpg", "jpeg", "png", "gif", "bmp", "webp", "tiff", "svg"): return "images"
        if ext in ("pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "epub", "rtf", "csv"): return "docs"
        return "file"

    def _mime_of(self, filename: str) -> str:
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"

    def _atomic_write_json(self, path: str, data: Any) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    # ------------------- index IO -------------------

    def _load_index(self) -> List[Dict[str, Any]]:
        try:
            with open(self.INDEX_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict): return data.get("files", []) or []
            if isinstance(data, list): return data
        except Exception:
            pass
        return []

    def _save_index(self, files: List[Dict[str, Any]]) -> None:
        self._atomic_write_json(self.INDEX_PATH, {"files": files})

    def _merge_index(self, new_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        existing = self._load_index()
        by_stored = {it.get("stored") or it.get("url"): it for it in existing}
        for it in new_items:
            key = it.get("stored") or it.get("url")
            if key not in by_stored:
                existing.append(it)
        return existing

    def _scan_media_dir(self) -> List[Dict[str, Any]]:
        """Сканирует /media и собирает новый список мета."""
        items: List[Dict[str, Any]] = []
        for fname in os.listdir(self.MEDIA_DIR):
            ap = os.path.join(self.MEDIA_DIR, fname)
            if not os.path.isfile(ap): continue
            st = os.stat(ap)
            items.append({
                "id": uuid.uuid4().hex[:12],
                "name": fname,
                "stored": fname,
                "url": f"/media/{fname}",
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "mime": self._mime_of(fname),
                "kind": self._kind_by_ext(fname),
                "tags": []
            })
        return items

    # ------------------- routes -------------------

    def _configure_routes(self) -> None:
        app = self.app

        @app.after_request
        def add_headers(resp):
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
            resp.headers["Accept-Ranges"] = "bytes"
            resp.headers["Cache-Control"] = "no-store"
            return resp

        # Универсальный OPTIONS для CORS
        @app.route("/api/<path:_any>", methods=["OPTIONS"])
        def any_options(_any):
            return make_response(("", 204))

        # Health
        @app.route("/health")
        def health():
            return jsonify({"ok": True})

        # UI
        @app.route("/")
        def ui_root():
            return send_from_directory(self.ROOT, "SalemMedia.html")

        @app.route("/ui")
        def ui_alias():
            return send_from_directory(self.ROOT, "SalemMedia.html")
        
        @app.route("/IconsStartPage/<path:fname>", methods=["GET"])
        @app.route("/MediaHub/IconsStartPage/<path:fname>", methods=["GET"])  # алиас, если страница грузится с /MediaHub/
        def ui_icons(fname: str):
            # лёгкая защита и нормализация
            fname = (fname or "").replace("\\", "/")
            if ".." in fname:
                return jsonify({"error": "forbidden"}), 403
        
            icons_dir = os.path.join(self.ROOT, "IconsStartPage")
            abs_path = os.path.abspath(os.path.join(icons_dir, fname))
        
            # не выходим за пределы каталога
            if not abs_path.startswith(os.path.abspath(icons_dir)):
                return jsonify({"error": "forbidden"}), 403
            if not os.path.isfile(abs_path):
                return jsonify({"error": "not found"}), 404
        
            resp = send_file(abs_path, mimetype=self._mime_of(abs_path))
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp
        
        # Необязательный бонус: стандартный /favicon.ico
        @app.route("/favicon.ico")
        def favicon():
            icons_dir = os.path.join(self.ROOT, "IconsStartPage")
            for name in ("favicon.ico", "favicon.png", "music.png"):
                p = os.path.join(icons_dir, name)
                if os.path.isfile(p):
                    resp = send_file(p, mimetype=self._mime_of(p))
                    resp.headers["Cache-Control"] = "public, max-age=86400"
                    return resp
            return jsonify({"error": "no favicon"}), 404


        # ---- Files listing ----
        @app.route("/api/files", methods=["GET"])
        def api_files():
            files = self._load_index()
            q = (request.args.get("q") or "").strip().lower()
            kind = (request.args.get("kind") or "").strip().lower()
            sort = (request.args.get("sort") or "name").lower()  # name|date|size
            order = (request.args.get("order") or "asc").lower() # asc|desc
            limit = int(request.args.get("limit", "0") or 0)
            offset = int(request.args.get("offset", "0") or 0)

            if q:
                files = [f for f in files if q in (f.get("name") or "").lower() or any(q in (t or "").lower() for t in f.get("tags", []))]
            if kind:
                files = [f for f in files if (f.get("kind") or "").lower() == kind]

            def key_name(x): return (x.get("name") or "").lower()
            def key_date(x): return x.get("mtime") or ""
            def key_size(x): return int(x.get("size") or 0)

            keyfn = key_name if sort == "name" else key_size if sort == "size" else key_date
            files = sorted(files, key=keyfn, reverse=(order=="desc"))

            total = len(files)
            if limit > 0:
                files = files[offset: offset+limit]

            return jsonify({"files": files, "total": total})
        
         # ---------- UI Config ----------
        @app.route("/api/config", methods=["GET", "POST"])
        def api_config():
            cfg_path = os.path.join(self.MEDIA_DIR, "config.json")

            if request.method == "GET":
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        data = {}
                except Exception:
                    data = {}
                return jsonify({"ok": True, "config": data})

            # POST — сохранить конфиг
            data = request.get_json(silent=True) or {}
            allowed = {"apiBase", "theme", "useServer", "autoplay"}
            cfg = {k: data.get(k) for k in allowed if k in data}
            try:
                self._atomic_write_json(cfg_path, cfg)
            except Exception as e:
                return jsonify({"error": f"save failed: {e}"}), 500
            return jsonify({"ok": True})  # ← ЭТОГО НЕ ХВАТАЛО


        # ---- Upload ----
        @app.route("/api/upload", methods=["POST"])
        def api_upload():
            if "files" not in request.files:
                return jsonify({"error": "Нет файлов (ожидаю поле 'files')"}), 400

            uploaded = request.files.getlist("files")
            if not uploaded:
                return jsonify({"error": "Пустой список файлов"}), 400

            saved_items: List[Dict[str, Any]] = []
            for file in uploaded:
                orig_name = self._safe_name(file.filename or "file")
                uid = uuid.uuid4().hex[:8]
                base, ext = os.path.splitext(orig_name)
                stored_name = self._safe_name(f"{uid}_{base}{ext}")
                path = os.path.join(self.MEDIA_DIR, stored_name)
                file.save(path)

                st = os.stat(path)
                item = {
                    "id": uuid.uuid4().hex[:12],
                    "name": orig_name,
                    "stored": stored_name,
                    "url": f"/media/{stored_name}",
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                    "mime": self._mime_of(stored_name),
                    "kind": self._kind_by_ext(stored_name),
                    "tags": []
                }
                saved_items.append(item)

            merged = self._merge_index(saved_items)
            self._save_index(merged)
            return jsonify({"ok": True, "files": saved_items})

        # ---- Single file meta ----
        @app.route("/api/file/<path:stored>", methods=["GET"])
        def api_file(stored: str):
            stored = stored.replace("\\", "/")
            files = self._load_index()
            for it in files:
                if it.get("stored") == stored:
                    return jsonify({"file": it})
            return jsonify({"error": "not found"}), 404

        # ---- Update meta (name/tags) ----
        # --- ДОБАВКА К СЕРВЕРУ: полноценный бэкенд для тегов/очистки/удаления/переименования ---

        @app.route("/api/meta", methods=["POST"])
        def api_meta():
            """
            Обновляет метаданные файла (теги/произвольные свойства).
            Body JSON: { stored: "xxxx.ext", tags?: [..], props?: {..} }
            """
            data = request.get_json(silent=True) or {}
            stored = (data.get("stored") or "").strip()
            if not stored:
                return jsonify({"error": "stored is required"}), 400

            files = self._load_index()
            updated = False
            for it in files:
                if it.get("stored") == stored or it.get("url") == f"/media/{stored}":
                    if isinstance(data.get("tags"), list):
                        # ограничим длину и приведём к строкам
                        it["tags"] = [str(t)[:128] for t in data["tags"]][:128]
                    if isinstance(data.get("props"), dict):
                        # лёгкая нормализация ключей/значений
                        it["props"] = {str(k)[:64]: (v if isinstance(v, (int, float, bool)) else str(v)[:1024])
                                       for k, v in data["props"].items()}
                    updated = True
                    break

            # если в индексе нет, но файл на диске есть — создадим запись
            if not updated:
                path = os.path.join(self.MEDIA_DIR, stored)
                if os.path.isfile(path):
                    st = os.stat(path)
                    files.append({
                        "id": uuid.uuid4().hex[:12],
                        "name": os.path.basename(stored),
                        "stored": stored,
                        "url": f"/media/{stored}",
                        "size": st.st_size,
                        "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                        "mime": self._mime_of(stored),
                        "kind": self._kind_by_ext(stored),
                        "tags": [str(t) for t in (data.get("tags") or [])],
                        "props": data.get("props") or {},
                    })
                    updated = True

            if not updated:
                return jsonify({"error": "not found"}), 404

            self._save_index(files)
            return jsonify({"ok": True})

        @app.route("/api/delete", methods=["POST"])
        def api_delete():
            """
            Удаляет один файл с диска и из индекса.
            Body JSON: { stored: "xxxx.ext" } или { url: "/media/xxxx.ext" }
            """
            data = request.get_json(silent=True) or {}
            stored = data.get("stored")
            url = data.get("url")
            if (not stored) and url:
                if url.startswith("/media/"): stored = url.split("/media/", 1)[1]
                else: return jsonify({"error":"bad url"}), 400
            if not stored:
                return jsonify({"error":"stored is required"}), 400

            # защита от traversal
            stored = stored.replace("\\", "/")
            if ".." in stored:
                return jsonify({"error":"forbidden"}), 403

            path = os.path.join(self.MEDIA_DIR, stored)
            files = self._load_index()
            before = len(files)
            files = [it for it in files if it.get("stored") != stored and it.get("url") != f"/media/{stored}"]

            # удаляем с диска молча, даже если нет в индексе
            try:
                if os.path.isfile(path):
                    os.remove(path)
            except Exception as e:
                # не валим запрос, просто сообщим
                self.app.logger.warning(f"delete failed for {path}: {e}")

            self._save_index(files)
            return jsonify({"ok": True, "removed_from_index": before - len(files)})

        @app.route("/api/clear", methods=["POST"])
        def api_clear():
            """
            Полная очистка каталога media (кроме index.json) и индекса.
            Body JSON: { wipe: true } — простая защита от случайных кликов.
            """
            data = request.get_json(silent=True) or {}
            if not data.get("wipe"):
                return jsonify({"error":"confirm wipe=true"}), 400

            # удаляем все файлы из media, кроме index.json
            for fname in os.listdir(self.MEDIA_DIR):
                if fname == os.path.basename(self.INDEX_PATH):
                    continue
                fpath = os.path.join(self.MEDIA_DIR, fname)
                try:
                    if os.path.isfile(fpath):
                        os.remove(fpath)
                except Exception as e:
                    self.app.logger.warning(f"clear skip {fpath}: {e}")

            # чистим индекс
            self._save_index([])
            return jsonify({"ok": True})

        @app.route("/api/rename", methods=["POST"])
        def api_rename():
            """
            Переименовывает сохранённый файл на диске + обновляет индекс.
            Body JSON: { stored: "old.ext", new_stored?: "new.ext", new_name?: "Показ. имя" }
            Если new_stored не задан — сгенерируем безопасное на основе new_name или old.
            """
            data = request.get_json(silent=True) or {}
            stored_old = (data.get("stored") or "").strip()
            if not stored_old:
                return jsonify({"error":"stored is required"}), 400

            new_stored = (data.get("new_stored") or "").strip()
            new_name = (data.get("new_name") or "").strip()

            # нормализуем
            if not new_stored:
                base_old, ext = os.path.splitext(stored_old)
                base = self._safe_name(new_name or base_old)
                # не теряем расширение
                if ext and not base.endswith(ext):
                    new_stored = f"{base}{ext}"
                else:
                    new_stored = base

            # защита от traversal
            for v in (stored_old, new_stored):
                if ".." in v or "/" in v or "\\" in v:
                    return jsonify({"error":"bad name"}), 400

            src = os.path.join(self.MEDIA_DIR, stored_old)
            dst = os.path.join(self.MEDIA_DIR, new_stored)
            if not os.path.isfile(src):
                return jsonify({"error":"not found"}), 404
            if os.path.exists(dst):
                # добавим уникальный хвост
                uid = uuid.uuid4().hex[:6]
                base, ext = os.path.splitext(new_stored)
                new_stored = f"{base}_{uid}{ext}"
                dst = os.path.join(self.MEDIA_DIR, new_stored)

            os.rename(src, dst)

            # обновляем индекс
            files = self._load_index()
            for it in files:
                if it.get("stored") == stored_old or it.get("url") == f"/media/{stored_old}":
                    it["stored"] = new_stored
                    it["url"] = f"/media/{new_stored}"
                    if new_name:
                        it["name"] = new_name
                    # обновим mime/kind/mtime/size
                    st = os.stat(dst)
                    it["size"] = st.st_size
                    it["mtime"] = datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
                    it["mime"] = self._mime_of(new_stored)
                    it["kind"] = self._kind_by_ext(new_stored)
                    break
            self._save_index(files)
            return jsonify({"ok": True, "stored": new_stored, "url": f"/media/{new_stored}"})

        @app.route("/api/stats", methods=["GET"])
        def api_stats():
            """
            Небольшая сводка по библиотеке.
            """
            files = self._load_index()
            total = len(files)
            by_kind = {}
            total_size = 0
            for it in files:
                k = it.get("kind") or "file"
                by_kind[k] = by_kind.get(k, 0) + 1
                total_size += int(it.get("size") or 0)
            return jsonify({
                "ok": True,
                "total": total,
                "by_kind": by_kind,
                "total_size": total_size
            })


        # ---- Media with Range (seek) ----
        @app.route("/media/<path:fname>", methods=["GET"])
        def media(fname: str):
            fname = fname.replace("\\", "/")
            if ".." in fname:
                return jsonify({"error": "forbidden"}), 403

            abs_path = os.path.abspath(os.path.join(self.MEDIA_DIR, fname))
            if not abs_path.startswith(self.MEDIA_DIR):
                return jsonify({"error": "forbidden"}), 403
            if not os.path.isfile(abs_path):
                return jsonify({"error": "not found"}), 404

            file_size = os.path.getsize(abs_path)
            range_header = request.headers.get("Range")
            mime = self._mime_of(abs_path)

            if not range_header:
                return send_file(abs_path, mimetype=mime, as_attachment=False, conditional=True)

            # Partial content
            try:
                units, rng = range_header.split("=")
                if units.strip() != "bytes":
                    raise ValueError
                start_s, end_s = (rng.split("-") + [""])[:2]
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else file_size - 1
                end = min(end, file_size - 1)
                if start < 0 or start > end:
                    raise ValueError
            except Exception:
                return Response(status=416)

            length = end - start + 1

            def generate():
                with open(abs_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    chunk = 8192 * 16
                    while remaining > 0:
                        data = f.read(min(chunk, remaining))
                        if not data:
                            break
                        yield data
                        remaining -= len(data)

            rv = Response(generate(), status=206, mimetype=mime, direct_passthrough=True)
            rv.headers.add("Content-Range", f"bytes {start}-{end}/{file_size}")
            rv.headers.add("Content-Length", str(length))
            return rv
        
        # ---- Albums (collections) ----
        # Храним альбомы в media/albums.json  формат: {"albums":[{"name":..., "created":..., "updated":..., "items":[stored,...], "tags":[...]}]}
        @app.route("/api/albums", methods=["GET", "POST"])
        def api_albums():
            albums_path = os.path.join(self.MEDIA_DIR, "albums.json")

            def load_albums():
                try:
                    with open(albums_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data.get("albums", []) or []
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass
                return []

            def save_albums(albums):
                self._atomic_write_json(albums_path, {"albums": albums})

            if request.method == "GET":
                albums = load_albums()
                # resolve=1 → прикладываем развёрнутые метаданные по items из index.json
                if (request.args.get("resolve") or "0") in ("1", "true", "yes"):
                    index = {it.get("stored"): it for it in self._load_index()}
                    resolved = []
                    for a in albums:
                        meta_items = [index.get(st) for st in a.get("items", []) if st in index]
                        a2 = dict(a)
                        a2["items_meta"] = meta_items
                        resolved.append(a2)
                    return jsonify({"albums": resolved})
                return jsonify({"albums": albums})

            # POST → создать новый альбом
            data = request.get_json(silent=True) or {}
            name = self._safe_name(data.get("name") or "").strip()
            items = data.get("items") or []
            tags = data.get("tags") or []
            if not name:
                return jsonify({"error": "name required"}), 400
            if not isinstance(items, list) or not all(isinstance(x, str) for x in items):
                return jsonify({"error": "items must be a list of stored strings"}), 400
            if not isinstance(tags, list):
                return jsonify({"error": "tags must be a list"}), 400

            albums = load_albums()
            if any(a.get("name") == name for a in albums):
                return jsonify({"error": "album already exists"}), 409

            now = self._now_iso()
            albums.append({
                "name": name,
                "created": now,
                "updated": now,
                "items": [self._safe_name(x) for x in items],
                "tags": [str(t)[:128] for t in tags]
            })
            save_albums(albums)
            return jsonify({"ok": True, "album": name})

        @app.route("/api/albums/<string:name>", methods=["GET", "PATCH", "DELETE"])
        def api_album_name(name: str):
            albums_path = os.path.join(self.MEDIA_DIR, "albums.json")

            def load_albums():
                try:
                    with open(albums_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        return data.get("albums", []) or []
                    if isinstance(data, list):
                        return data
                except Exception:
                    pass
                return []

            def save_albums(albums):
                self._atomic_write_json(albums_path, {"albums": albums})

            name = self._safe_name(name).strip()
            albums = load_albums()
            idx = next((i for i, a in enumerate(albums) if a.get("name") == name), -1)
            if idx < 0:
                return jsonify({"error": "not found"}), 404

            if request.method == "GET":
                album = dict(albums[idx])
                # resolve=1 → прикладываем развёрнутые метаданные по items из index.json
                if (request.args.get("resolve") or "0") in ("1", "true", "yes"):
                    index = {it.get("stored"): it for it in self._load_index()}
                    album["items_meta"] = [index.get(st) for st in album.get("items", []) if st in index]
                return jsonify({"album": album})

            if request.method == "DELETE":
                albums.pop(idx)
                save_albums(albums)
                return jsonify({"ok": True})

            # PATCH → операции над альбомом
            data = request.get_json(silent=True) or {}
            op = (data.get("op") or "").lower().strip()
            album = albums[idx]

            if op == "add":
                # добавить items: ["stored1", ...]
                items = data.get("items") or []
                if not isinstance(items, list):
                    return jsonify({"error": "items must be list"}), 400
                sset = set(album.get("items", []))
                for st in items:
                    sset.add(self._safe_name(str(st)))
                album["items"] = list(sset)

            elif op == "remove":
                # убрать items
                items = data.get("items") or []
                if not isinstance(items, list):
                    return jsonify({"error": "items must be list"}), 400
                rm = {self._safe_name(str(st)) for st in items}
                album["items"] = [x for x in album.get("items", []) if x not in rm]

            elif op == "set":
                # заменить полный список items
                items = data.get("items") or []
                if not isinstance(items, list):
                    return jsonify({"error": "items must be list"}), 400
                album["items"] = [self._safe_name(str(st)) for st in items]

            elif op == "rename":
                # переименовать альбом
                new_name = self._safe_name(data.get("new_name") or "").strip()
                if not new_name:
                    return jsonify({"error": "new_name required"}), 400
                if any(a.get("name") == new_name for a in albums if a is not album):
                    return jsonify({"error": "album with new_name already exists"}), 409
                album["name"] = new_name
                name = new_name  # для возвращаемого значения

            elif op == "tags":
                # задать/заменить список тегов альбома
                tags = data.get("tags") or []
                if not isinstance(tags, list):
                    return jsonify({"error": "tags must be list"}), 400
                album["tags"] = [str(t)[:128] for t in tags]

            else:
                return jsonify({"error": "unknown op (use add|remove|set|rename|tags)"}), 400

            album["updated"] = self._now_iso()
            albums[idx] = album
            save_albums(albums)
            return jsonify({"ok": True, "album": album})
        
        

    # --------------- integration ---------------

    @property
    def wsgi(self):
        return self.app

    def run(self, debug: bool = False):
        print(f"📡 SalemMediaServer @ http://{self.host}:{self.port}  (root={self.ROOT})")
        self.app.run(self.host, self.port, debug=debug, threaded=True)

        



if __name__ == "__main__":
    SalemMediaServer().run(debug=False)
