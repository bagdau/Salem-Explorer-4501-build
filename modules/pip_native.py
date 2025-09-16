# modules/pip_native.py
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QObject, QUrl
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent
from PyQt5.QtMultimediaWidgets import QVideoWidget

# ───── потрошитель ссылок через yt-dlp (в отдельном потоке) ─────

class _FetchWorker(QObject):
    finished = pyqtSignal(str, str)  # (stream_url, err)
    def __init__(self, page_url: str):
        super().__init__()
        self.page_url = page_url

    def run(self):
        try:
            # Ленивая зависимость: yt-dlp (pip install yt-dlp)
            import yt_dlp
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "noplaylist": True,
                "format": "bestvideo+bestaudio/best",
                "merge_output_format": "mp4",
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.page_url, download=False)
                # Пытаемся взять прямой URL
                if "url" in info:
                    return self.finished.emit(info["url"], "")
                # Иногда нужен формат
                fmts = info.get("formats") or []
                fmts = [f for f in fmts if f.get("url")]
                # приоритет mp4/hls
                def score(f):
                    ext = (f.get("ext") or "").lower()
                    tbr = f.get("tbr") or 0
                    return (ext in ("mp4", "m4v", "mov", "m3u8"))*100000 + tbr
                best = sorted(fmts, key=score, reverse=True)[0] if fmts else None
                url = best.get("url") if best else ""
                self.finished.emit(url or "", "" if url else "NO_URL")
        except Exception as e:
            self.finished.emit("", str(e))

# ───── окно нативного PiP на QMediaPlayer ─────

class PiPMediaWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setObjectName("PiPMediaWindow")
        self.resize(560, 320)

        self.player = QMediaPlayer(self)
        self.video = QVideoWidget(self)
        self.player.setVideoOutput(self.video)

        self.btn_play = QPushButton("⏯")
        self.btn_mute = QPushButton("🔇")
        self.btn_close = QPushButton("✕")
        self.seek = QSlider(Qt.Horizontal); self.seek.setRange(0, 1000)
        self.vol = QSlider(Qt.Horizontal); self.vol.setRange(0, 100); self.vol.setValue(50)
        self.player.setVolume(50)

        ctrls = QHBoxLayout()
        ctrls.addWidget(self.btn_play)
        ctrls.addWidget(self.btn_mute)
        ctrls.addWidget(QLabel("Seek"))
        ctrls.addWidget(self.seek, 1)
        ctrls.addWidget(QLabel("Vol"))
        ctrls.addWidget(self.vol)
        ctrls.addWidget(self.btn_close)

        root = QVBoxLayout(self); root.setContentsMargins(8,8,8,8)
        root.addWidget(self.video, 1)
        root.addLayout(ctrls)

        # события
        self.btn_close.clicked.connect(self.close)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_mute.clicked.connect(self._toggle_mute)
        self.vol.valueChanged.connect(self.player.setVolume)
        self.player.positionChanged.connect(self._on_pos)
        self.player.durationChanged.connect(self._on_dur)
        self.seek.sliderMoved.connect(self._on_seek)

        # DRAG
        self._drag = None

    # публичное API
    def play_url(self, url: str):
        self.player.setMedia(QMediaContent(QUrl(url)))
        self.player.play()

    # простые контролы
    def _toggle_play(self):
        if self.player.state() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _toggle_mute(self):
        self.player.setMuted(not self.player.isMuted())

    def _on_pos(self, pos):
        dur = max(1, self.player.duration())
        self.seek.blockSignals(True)
        self.seek.setValue(int(pos / dur * 1000))
        self.seek.blockSignals(False)

    def _on_dur(self, dur):
        # ничего, прогресс считаем в процентах
        pass

    def _on_seek(self, v):
        dur = self.player.duration()
        self.player.setPosition(int(dur * (v/1000.0)))

    # drag window
    def mousePressEvent(self, e):
        if e.button() == 1:
            self._drag = (e.globalPos(), self.frameGeometry().topLeft())

    def mouseMoveEvent(self, e):
        if self._drag:
            g0, top0 = self._drag
            self.move(top0 + (e.globalPos()-g0))

    def mouseReleaseEvent(self, e):
        self._drag = None

    def closeEvent(self, e):
        try:
            self.player.stop()
        except: pass
        self.closed.emit()
        super().closeEvent(e)
