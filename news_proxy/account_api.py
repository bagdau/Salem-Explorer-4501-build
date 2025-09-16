import os, time, sqlite3, secrets
from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


class AccountAPI:
    def __init__(self, db_path=None, avatar_dir=None):
        self.bp = Blueprint("api", __name__, url_prefix="/api")

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.DB_PATH = db_path or os.path.join(base_dir, "account.db")
        self.AVATAR_DIR = avatar_dir or os.path.join(base_dir, "static", "avatars")
        os.makedirs(self.AVATAR_DIR, exist_ok=True)

        # маршруты
        self.bp.add_url_rule("/register.php", "register", self.register, methods=["POST"])
        self.bp.add_url_rule("/login.php", "login", self.login, methods=["POST"])
        self.bp.add_url_rule("/logout.php", "logout", self.logout, methods=["POST"])
        self.bp.add_url_rule("/profile.php", "profile", self.profile, methods=["GET"])
        self.bp.add_url_rule("/update_profile.php", "update_profile", self.update_profile, methods=["POST"])
        self.bp.add_url_rule("/upload_avatar.php", "upload_avatar", self.upload_avatar, methods=["POST"])

    # --- DB helpers ---
    def _db(self):
        conn = sqlite3.connect(self.DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        with self._db() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              email TEXT UNIQUE NOT NULL,
              name  TEXT NOT NULL,
              password_hash TEXT NOT NULL,
              role TEXT,
              location TEXT,
              lang TEXT DEFAULT 'kk',
              avatar TEXT,
              created_at INTEGER DEFAULT (strftime('%s','now'))
            )""")

    def _row_to_profile(self, r):
        if not r: return None
        return {
            "id": r["id"],
            "email": r["email"],
            "name": r["name"],
            "role": r["role"] or "",
            "location": r["location"] or "",
            "lang": r["lang"] or "kk",
            "avatar": r["avatar"] or "",
        }

    def _me(self):
        uid = session.get("uid")
        if not uid: return None
        with self._db() as c:
            r = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
            return r

    # --- routes ---
    def register(self):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not name or not email or not password:
            return jsonify({"error": "Заполните все поля"}), 400
        if len(password) < 6:
            return jsonify({"error": "Пароль должен быть ≥ 6 символов"}), 400

        try:
            with self._db() as c:
                c.execute(
                    "INSERT INTO users (email,name,password_hash) VALUES (?,?,?)",
                    (email, name, generate_password_hash(password)),
                )
        except sqlite3.IntegrityError:
            return jsonify({"error": "Пользователь с таким email уже существует"}), 400

        return jsonify({"ok": True})

    def login(self):
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        if not email or not password:
            return jsonify({"error": "Укажите email и пароль"}), 400

        with self._db() as c:
            r = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not r or not check_password_hash(r["password_hash"], password):
            return jsonify({"error": "Неверный email или пароль"}), 400

        session["uid"] = int(r["id"])
        session.permanent = True
        return jsonify({"ok": True})

    def logout(self):
        session.pop("uid", None)
        return jsonify({"ok": True})

    def profile(self):
        r = self._me()
        if not r:
            return jsonify({"id": None})
        return jsonify(self._row_to_profile(r))

    def update_profile(self):
        r = self._me()
        if not r:
            return jsonify({"error": "Требуется вход"}), 401

        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        role = (data.get("role") or "").strip()
        location = (data.get("location") or "").strip()
        lang = (data.get("lang") or "kk").strip() or "kk"

        if not name or not email:
            return jsonify({"error": "Имя и email обязательны"}), 400

        try:
            with self._db() as c:
                c.execute("""UPDATE users SET email=?, name=?, role=?, location=?, lang=? WHERE id=?""",
                          (email, name, role, location, lang, r["id"]))
                r2 = c.execute("SELECT * FROM users WHERE id=?", (r["id"],)).fetchone()
        except sqlite3.IntegrityError:
            return jsonify({"error": "Этот email занят другим пользователем"}), 400

        return jsonify({"profile": self._row_to_profile(r2)})

    def upload_avatar(self):
        r = self._me()
        if not r:
            return jsonify({"error": "Требуется вход"}), 401

        f = request.files.get("avatar")
        if not f:
            return jsonify({"error": "Файл не передан"}), 400

        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(0)
        if size > 2*1024*1024:
            return jsonify({"error": "Файл слишком большой (≤2MB)"}), 400

        ext = os.path.splitext(f.filename or "")[1].lower()[:8]
        fname = f"{int(time.time())}_{secrets.token_hex(4)}{ext}"
        path = os.path.join(self.AVATAR_DIR, secure_filename(fname))
        f.save(path)

        url = f"/static/avatars/{fname}"
        with self._db() as c:
            c.execute("UPDATE users SET avatar=? WHERE id=?", (url, r["id"]))
        return jsonify({"url": url})
