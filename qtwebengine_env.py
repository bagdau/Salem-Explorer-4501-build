# qtwebengine_env.py — runtime hook for PyQt5 WebEngine (Windows)
import os
# Без этого QtWebEngine в собранном .exe на Windows часто падает при старте
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
# при желании можно включить GPU (если вдруг нужна аппаратная отрисовка)
# os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--enable-gpu")
