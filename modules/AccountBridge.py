# AccountBridge.py — мост Qt WebChannel для записи/чтения JSON
# Сохраняет массив учётных записей в ./UserData/userLogin.json

import json
from pathlib import Path

try:
    from PyQt5.QtCore import QObject, pyqtSlot
except ImportError:
    # Если используешь PyQt6 — раскомментируй ниже и поменяй импорт в проекте
    # from PyQt6.QtCore import QObject, pyqtSlot
    from PyQt5.QtCore import QObject, pyqtSlot  # fallback

class AccountBridge(QObject):
    def __init__(self, base_dir: Path | None = None, parent=None):
        super().__init__(parent)
        root = Path(base_dir) if base_dir else Path(__file__).resolve().parent
        self.user_dir = root / "UserData"
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.file = self.user_dir / "userLogin.json"

    @pyqtSlot(str, result=bool)
    def saveUser(self, json_str: str) -> bool:
        """Принимает строку JSON (ожидается массив объектов), сохраняет в файл."""
        try:
            data = json.loads(json_str)
            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print("[AccountBridge] saveUser error:", e)
            return False

    @pyqtSlot(result=str)
    def getUser(self) -> str:
        """Возвращает содержимое файла JSON как строку. Пустую строку, если нет файла."""
        try:
            if self.file.exists():
                return self.file.read_text(encoding="utf-8")
        except Exception as e:
            print("[AccountBridge] getUser error:", e)
        return ""
