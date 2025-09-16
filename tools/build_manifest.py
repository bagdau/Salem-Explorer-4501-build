# tools/build_manifest.py
from __future__ import annotations
import os, sys, json, hashlib, time, argparse, gzip
from pathlib import Path
from typing import Iterable, Dict, Any, List

DEFAULT_INCLUDE_DIRS = [
    "img/icons",
    "modules/icons",
    "news_proxy/IconsStartPage",
    "news_proxy/img",
    "news_proxy/static/css",
    "news_proxy/static/js",
    "news_proxy/static/img",
    "news_proxy/static/avatars",
    "news_proxy/static/uploads",
    "news_proxy/static/wallpapers",
]

HOT_EXT = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico", ".css", ".js", ".html"}

def log(msg: str):
    print(f"[manifest] {msg}", flush=True)

def detect_project_root(arg_root: str | None) -> Path:
    """
    Определяем корень проекта:
    - если передан аргумент --root — берём его,
    - иначе берём папку, где лежит этот файл (tools/..) и поднимаемся на один уровень,
    - если там нет ни img/, ни news_proxy/ — fallback на CWD.
    """
    if arg_root:
        p = Path(arg_root).resolve()
    else:
        here = Path(__file__).resolve()
        p = here.parent.parent  # tools/.. -> корень
    if not ((p / "img").exists() or (p / "news_proxy").exists()):
        # возможно запускают из dev-окружения — используем CWD
        p = Path.cwd().resolve()
    return p

def iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in HOT_EXT:
            yield p

def sha1(path: Path, chunk=256*1024) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b: break
            h.update(b)
    return h.hexdigest()

def build_manifest(project_root: Path, include_dirs: List[str], out_path: Path, do_hash=True) -> Dict[str, Any]:
    t0 = time.time()
    entries = []
    total_size = 0
    total_files = 0

    for rel in include_dirs:
        root = (project_root / rel).resolve()
        if not root.exists():
            log(f"skip (not found): {rel}")
            continue
        cnt_dir = 0
        for f in iter_files(root):
            try:
                s = f.stat()
                size = s.st_size
                total_size += size
                total_files += 1
                cnt_dir += 1
                entries.append({
                    "rel": str(f.relative_to(project_root).as_posix()),
                    "size": size,
                    "mtime": int(s.st_mtime),
                    "sha1": (sha1(f) if (do_hash and size <= 2_000_000) else None),
                })
            except Exception as e:
                log(f"warn: cannot read {f}: {e}")
        log(f"ok: {rel} → {cnt_dir} files")

    manifest = {
        "version": 1,
        "generated_at": int(time.time()),
        "elapsed_ms": int((time.time() - t0) * 1000),
        "project_root": str(project_root.as_posix()),
        "total_entries": len(entries),
        "total_size": total_size,
        "entries": entries,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    log(f"written: {out_path}  files={len(entries)}  ~{total_size/1024:.0f} KB  in {manifest['elapsed_ms']} ms")
    return manifest

def build_manifest_gzip(src_json: Path, out_gz: Path):
    b = src_json.read_bytes()
    with gzip.open(out_gz, "wb", compresslevel=6) as z:
        z.write(b)
    log(f"written: {out_gz}  ({len(b)} bytes gzipped)")

def parse_args():
    ap = argparse.ArgumentParser(description="Build assets manifest for Salem.")
    ap.add_argument("--root", help="Project root (if omitted, auto-detect).")
    ap.add_argument("--out", help="Output json (default: assets.manifest.json)", default="assets.manifest.json")
    ap.add_argument("--include", nargs="*", help="Dirs relative to root to include")
    ap.add_argument("--no-hash", action="store_true", help="Disable SHA1 for faster build")
    ap.add_argument("--gzip", action="store_true", help="Also write assets.manifest.json.gz")
    return ap.parse_args()

if __name__ == "__main__":
    args = parse_args()
    project_root = detect_project_root(args.root)
    include_dirs = args.include if args.include else DEFAULT_INCLUDE_DIRS
    out_json = (Path(args.out).resolve()
                if os.path.isabs(args.out)
                else (project_root / args.out).resolve())
    log(f"root={project_root}")
    log(f"out={out_json}")
    log(f"include={include_dirs}")
    mf = build_manifest(project_root, include_dirs, out_json, do_hash=not args.no_hash)
    if args.gzip:
        build_manifest_gzip(out_json, out_json.with_suffix(out_json.suffix + ".gz"))
