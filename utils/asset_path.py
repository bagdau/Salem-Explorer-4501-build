# utils/asset_path.py — безопасные пути к ресурсам (dev/заморозка)
import os, sys
def asset_path(rel: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, rel.replace("/", os.sep))
