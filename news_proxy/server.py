# server.py — Salem News Proxy (clean, patched)
# -*- coding: utf-8 -*-
import os, re, io, time, base64, random, hashlib, datetime, mimetypes
from collections import OrderedDict
from urllib.parse import urlparse, urljoin
from pathlib import Path
import requests
from flask import (
    Flask, request, jsonify, send_file, send_from_directory,
    make_response, redirect, Response
)

        # Тихий лог: скрываем строки со статусом 304
import logging
class _Skip304(logging.Filter):
    def filter(self, record):
        try:
            msg = record.getMessage()
        except Exception:
            return True
        return " 304 " not in msg  # пропускаем всё, кроме 304
logging.getLogger("werkzeug").addFilter(_Skip304())


class SalemServer:
    # ===== настройки =====
    TTL = 300
    LRU_CAP = 200
    FEED_TIMEOUT = 10
    HTTP_TIMEOUT = 12
    PROXY_MAX_BYTES = 8 * 1024 * 1024

    # канонический «дом»
    CANONICAL_HOME = "/ui"

    STATIC_MAX_AGE = 31536000  # 1 год
    HTML_NO_CACHE = "no-store"

    DEFAULT_FEEDS = [
        "https://news.google.com/rss?hl=ru&gl=KZ&ceid=KZ:ru",
        "https://news.yandex.ru/index.rss",
        "https://www.ixbt.com/export/ixbt_rss_full.xml",
    ]

    UA_POOL = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    ]
    DEFAULT_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru,en;q=0.9",
        "Connection": "keep-alive",
    }

    NEWSAPI_BASE = "https://newsapi.org/v2"
    NEWSAPI_TTL  = 300

    _PLACEHOLDER_PNG = base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
        b"/x8AAwMCAO2fZk8AAAAASUVORK5CYII="
    )
    

    def __init__(self, host: str = "127.0.0.1", port: int = 5000):
        self.host = host
        self.port = port

        # типы (некоторые окружения не отдают корректные mimetype)
        mimetypes.add_type("text/css", ".css")
        mimetypes.add_type("application/javascript", ".js")
        mimetypes.add_type("image/webp", ".webp")
        mimetypes.add_type("font/woff2", ".woff2")

        self.app = Flask(__name__, static_folder="static", static_url_path="/static")
        self.app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 31536000


        self.app = Flask(__name__, static_folder="static", static_url_path="/static")
        self.app.url_map.strict_slashes = False
        self.app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

        self.ROOT = os.path.dirname(os.path.abspath(__file__))
        self.IMG_DIR = os.path.join(self.ROOT, "img")
        os.makedirs(self.IMG_DIR, exist_ok=True)
        self._cache = OrderedDict()

        # NEWSAPI ключ
        self.NEWSAPI_KEY = os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or ""
        if not self.NEWSAPI_KEY:
            kp = os.path.join(self.ROOT, "NEWSAPI_KEY.txt")
            if os.path.isfile(kp):
                with open(kp, "r", encoding="utf-8") as fh:
                    self.NEWSAPI_KEY = fh.read().strip()

        self._install_hooks()
        self._try_register_account_api()
        self._register_routes()

    # ===== CORS/ошибки/health =====
    def _install_hooks(self):
        app = self.app

        @app.after_request
        def add_cors_and_cache(resp):
            # CORS
            resp.headers["Access-Control-Allow-Origin"] = "*"
            resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
            resp.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

            # Кэш-политики
            p = (request.path or "")
            if resp.status_code == 200:
                if p.startswith(("/static/", "/assets/", "/wallpapers/")):
                    # Длинный кэш для статики: браузер не будет ре-валидировать
                    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
                elif p in ("/", "/ui", "/wallpapers.html"):
                    # HTML не кэшируем, и главное — не ре-валидируем
                    resp.headers["Cache-Control"] = "no-store"
            return resp


        @app.route("/health")
        def health():
            return jsonify({"ok": True})

        @app.route("/api/<path:_any>", methods=["OPTIONS"])
        def any_options(_any):
            return make_response("", 204)

        @app.route("/api/health")
        def api_health():
            return jsonify({"ok": True})

        def _is_api(path: str) -> bool:
            return path.startswith("/api/")

        def _send_error_page(filename: str, code: int):
            if not filename.lower().endswith(".html"):
                filename += ".html"
            fp = os.path.join(self.ROOT, filename)
            if os.path.isfile(fp):
                # HTML без кэша
                resp = send_file(fp, mimetype="text/html; charset=utf-8", conditional=True)
                resp.headers["Cache-Control"] = self.HTML_NO_CACHE
                return resp, code
            return make_response(f"<h1>{code}</h1><p>Error</p>", code)

        @app.errorhandler(404)
        def handle_404(e):
            return (jsonify({"ok": False, "error": "not found", "code": 404}), 404) if _is_api(request.path) \
                   else _send_error_page("404Error", 404)

        @app.errorhandler(500)
        def handle_500(e):
            return (jsonify({"ok": False, "error": "server error", "code": 500}), 500) if _is_api(request.path) \
                   else _send_error_page("500Error", 500)

        @app.errorhandler(503)
        def handle_503(e):
            return (jsonify({"ok": False, "error": "service unavailable", "code": 503}), 503) if _is_api(request.path) \
                   else _send_error_page("503Error", 503)

    # ===== подключение аккаунтов (любой из двух вариантов) =====
    def _try_register_account_api(self):
        app = self.app
        try:
            from .account_api import AccountAPI  # type: ignore
            api = AccountAPI()
            app.register_blueprint(api.bp, url_prefix="/api")
            api.init_db()
            return
        except Exception:
            pass
        try:
            from .account_api import account_bp, init_db  # type: ignore
            app.register_blueprint(account_bp, url_prefix="/api")
            init_db()
            return
        except Exception:
            print("[account_api] не найден — роуты аккаунтов отключены.")

        @app.route("/account")
        def account_page():
            return send_from_directory(app.static_folder, "Account.html")

        @app.route("/account.js")
        def account_js():
            return send_from_directory(app.static_folder, "account.js")

    # ===== утилиты =====
    def _req_headers(self):
        h = dict(self.DEFAULT_HEADERS)
        h["User-Agent"] = random.choice(self.UA_POOL)
        return h

    def _fetch_url(self, url: str, timeout: float, stream: bool = False, headers: dict | None = None):
        base_h = self._req_headers()
        if headers:
            base_h.update({k: v for k, v in headers.items() if v})
        last = None
        for _ in range(3):
            try:
                r = requests.get(url, headers=base_h, timeout=timeout, stream=stream, allow_redirects=True)
                r.raise_for_status()
                return r
            except Exception as e:
                last = e
                time.sleep(0.25)
        raise last

    def _cache_get(self, key):
        it = self._cache.get(key)
        if not it: return None
        exp, val = it
        if time.time() >= exp:
            try: del self._cache[key]
            except Exception: pass
            return None
        self._cache.move_to_end(key, last=True)
        return val

    def _cache_set(self, key, value, ttl=None):
        exp = time.time() + max(1, int(self.TTL if ttl is None else ttl))
        self._cache[key] = (exp, value)
        self._cache.move_to_end(key, last=True)
        while len(self._cache) > self.LRU_CAP:
            self._cache.popitem(last=False)

    @staticmethod
    def _abs(url_base: str, maybe_rel: str) -> str:
        try: return urljoin(url_base, maybe_rel)
        except Exception: return maybe_rel

    @staticmethod
    def _fmt_date(dt_or_str) -> str:
        try:
            if isinstance(dt_or_str, (time.struct_time,)):
                dt = datetime.datetime.fromtimestamp(time.mktime(dt_or_str))
                return dt.strftime("%d.%m.%Y, %H:%M")
            if isinstance(dt_or_str, str):
                try:
                    return datetime.datetime.fromisoformat(dt_or_str.replace("Z","")).strftime("%d.%m.%Y, %H:%M")
                except Exception:
                    return dt_or_str
            return datetime.datetime.utcnow().strftime("%d.%m.%Y, %H:%M")
        except Exception:
            return ""

    # ===== вспомогательные отдачи =====
    def _safe_path(self, root_dir: str, name: str) -> str:
        name = (name or "").replace("\\", "/")
        if ".." in name: return ""
        abs_path = os.path.abspath(os.path.join(root_dir, name))
        return abs_path if abs_path.startswith(root_dir) else ""

    def _serve_html_file(self, name: str):
        fp = self._safe_path(self.ROOT, name)
        if fp and os.path.isfile(fp):
            resp = send_file(fp, mimetype="text/html; charset=utf-8", conditional=True)
            # заголовок Cache-Control проставится в after_request
            return resp
        return make_response(f"{name} not found", 404)

    # ===== роуты =====
    def _register_routes(self):
        app = self.app

        # --- Mailto/Compose ---
        MAIL_COMPOSE_BASE = os.environ.get("MAIL_COMPOSE_BASE", "http://127.0.0.1:3232/compose")

        @app.route("/mailto", methods=["GET"])
        def mailto_redirect():
            qs = request.query_string.decode("utf-8", errors="ignore")
            return redirect(f"{MAIL_COMPOSE_BASE}?{qs}" if qs else MAIL_COMPOSE_BASE, code=302)

        @app.route("/compose", methods=["GET", "POST"])
        def proxy_compose():
            target = MAIL_COMPOSE_BASE
            try:
                if request.method == "POST":
                    resp = requests.post(target, data=request.form, timeout=15)
                else:
                    resp = requests.get(target, params=request.args, timeout=15)
            except Exception as e:
                return make_response(f"Compose proxy error: {e}", 502)
            return Response(
                resp.content,
                status=resp.status_code,
                headers={k: v for k, v in resp.headers.items() if k.lower() != "content-encoding"}
            )

        # --- Корень/UI/статик ---
        @app.route("/", methods=["GET", "HEAD"])
        def root_index():
            # единая точка входа — всегда /ui
            if self.CANONICAL_HOME != "/" and request.path == "/":
                # 308 сохраняет метод/тело запросов
                return redirect(self.CANONICAL_HOME, code=308)
            return self._serve_html_file("index.html")

        @app.route("/ui", methods=["GET", "HEAD"])
        def ui_index():
            return self._serve_html_file("index.html")

        @app.route("/wallpapers.html", methods=["GET", "HEAD"])
        def wallpapers_page():
            return self._serve_html_file("wallpapers.html")

        @app.route("/favicon.ico", methods=["GET", "HEAD"])
        def favicon():
            fp = self._safe_path(self.ROOT, "favicon.ico")
            if fp and os.path.isfile(fp):
                resp = send_file(fp, mimetype="image/x-icon", conditional=True)
            else:
                resp = make_response(self._PLACEHOLDER_PNG, 200)
                resp.headers["Content-Type"] = "image/png"
            resp.headers["Cache-Control"] = "public, max-age=86400"
            return resp

        @app.route("/static/<path:name>", methods=["GET", "HEAD"])
        def static_files(name: str):
            static_dir = os.path.join(self.ROOT, "static")
            fp = self._safe_path(static_dir, name)
            if not fp or not os.path.isfile(fp):
                return make_response("not found", 404)
            mt = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            return send_file(fp, mimetype=mt, conditional=True)

        @app.route("/assets/<path:name>", methods=["GET", "HEAD"])
        def assets_files(name: str):
            assets_dir = os.path.join(self.ROOT, "assets")
            fp = self._safe_path(assets_dir, name)
            if not fp or not os.path.isfile(fp):
                return make_response("not found", 404)
            mt = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            return send_file(fp, mimetype=mt, conditional=True)

        @app.route("/wallpapers/<path:name>", methods=["GET", "HEAD"])
        def wallpapers_files(name: str):
            wallpapers_dir = os.path.join(self.ROOT, "wallpapers")
            fp = self._safe_path(wallpapers_dir, name)
            if not fp or not os.path.isfile(fp):
                return make_response("not found", 404)
            mt = mimetypes.guess_type(fp)[0] or "application/octet-stream"
            return send_file(fp, mimetype=mt, conditional=True)

    # ===== запуск/wsgi =====
    def run(self, debug: bool = False):
        print(f"📰 SalemNews @ http://{self.host}:{self.port}  (root={self.ROOT})")
        self.app.run(self.host, self.port, debug=debug, threaded=True)

    @property
    def wsgi(self):
        return self.app

if __name__ == "__main__":
    SalemServer(host="127.0.0.1", port=5000).run(debug=False)
