# pip_mode.py — PyQt5
# Улучшенный PiP для QWebEngineView:
#   • Стеклянный стиль с неон-акцентами (GX-вибрации)
#   • Плавающая нижняя панель с fade-анимацией (автоскрытие)
#   • Таймлайн/перемотка, Play/Pause, Mute
#   • Горячие клавиши: Space (Play/Pause), M (Mute), F (локальный FS),
#                      ←/→ (−/+ 5s), ↑/↓ (громкость ±10%), Esc — закрыть
#   • Блокировка web-fullscreen YouTube, локальный fullscreen в рамках окна
#   • Сохранение позиции/размера окна (QSettings)

from PyQt5.QtCore import (
    Qt, QPoint, QRect, QTimer, pyqtSignal, QEvent, QSettings, QPropertyAnimation
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QFrame, QSlider, QLabel,
    QGraphicsOpacityEffect
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings


class PipWindow(QWidget):
    closed = pyqtSignal()
    RESIZE_MARGIN = 8

    def __init__(self, parent=None):
        super().__init__(
            parent,
            Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint
        )
        self.setObjectName("PipWindow")
        self.setMouseTracking(True)

        # --- state
        self._view = None
        self._drag_pos = None
        self._resizing = False
        self._resize_dir = None
        self._start_geom = None
        self._drag_started_in_gx = False
        self._local_fs = False
        self._seeking = False            # пользователь тащит слайдер
        self._last_duration = 0.0

        # --- root
        self._root = QFrame(self)
        self._root.setObjectName("pipRoot")
        self._root.setStyleSheet("""
            #pipRoot {
              background: rgba(15,17,23,0.72);
              border: 1px solid rgba(255,255,255,0.08);
              border-radius: 14px;
              backdrop-filter: blur(12px) saturate(1.2);
            }
            QToolButton {
              border: none; padding: 4px 10px; color: #e6edf3; font-size: 15px;
            }
            QToolButton:hover {
              background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #07fff344, stop:1 #ff007c44);
              border-radius: 9px;
            }
            QToolButton:pressed { background:#1b2234; }
            QLabel#timeLabel { color:#a9b4d6; padding:0 6px; }
            QSlider::groove:horizontal {
              height: 6px;
              margin: 6px 0;
              background: rgba(255,255,255,0.08);
              border-radius: 3px;
            }
            QSlider::handle:horizontal {
              background: #07fff3;
              border: 1px solid #0c1822;
              width: 12px; height: 12px;
              margin: -6px 0; border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
              background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #07fff3, stop:1 #ff007c);
              border-radius: 3px;
            }
        """)
        lay0 = QVBoxLayout(self)
        lay0.setContentsMargins(0, 0, 0, 0)
        lay0.addWidget(self._root)

        self._vbox = QVBoxLayout(self._root)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(0)

        self.resize(560, 320)

        # === GX overlay bar (внизу) ===
        self._gx = QWidget(self._root)
        self._gx.setObjectName("gxBar")
        self._gx.setAttribute(Qt.WA_StyledBackground, True)
        self._gx.setFixedHeight(44)
        gxl = QHBoxLayout(self._gx)
        gxl.setContentsMargins(10, 6, 10, 6)
        gxl.setSpacing(8)

        # Кнопки навигации и управления
        self.btn_back   = QToolButton(self._gx); self.btn_back.setText("◁")
        self.btn_fwd    = QToolButton(self._gx); self.btn_fwd.setText("▷")
        self.btn_play   = QToolButton(self._gx); self.btn_play.setText("▶")
        self.btn_mute   = QToolButton(self._gx); self.btn_mute.setText("🔇")
        self.btn_fs     = QToolButton(self._gx); self.btn_fs.setText("⛶")
        self.btn_close  = QToolButton(self._gx); self.btn_close.setText("✕")

        # Таймлайн и таймер-лейбл
        self.slider = QSlider(Qt.Horizontal, self._gx)
        self.slider.setRange(0, 1000)  # 0..1000 — проценты
        self.slider.setSingleStep(1)
        self.slider.setPageStep(25)
        self.lbl_time = QLabel("00:00 / 00:00", self._gx)
        self.lbl_time.setObjectName("timeLabel")

        # Компоновка
        gxl.addWidget(self.btn_back)
        gxl.addWidget(self.btn_fwd)
        gxl.addWidget(self.btn_play)
        gxl.addWidget(self.btn_mute)
        gxl.addSpacing(6)
        gxl.addWidget(self.slider, 1)
        gxl.addWidget(self.lbl_time)
        gxl.addSpacing(6)
        gxl.addWidget(self.btn_fs)
        gxl.addWidget(self.btn_close)

        # Эффект прозрачности и анимации для GX
        self._gx_fx = QGraphicsOpacityEffect(self._gx)
        self._gx.setGraphicsEffect(self._gx_fx)
        self._gx_fx.setOpacity(1.0)
        self._anim = None

        # Автоскрытие GX-панели
        self._gx_timer = QTimer(self)
        self._gx_timer.setSingleShot(True)
        self._gx_timer.timeout.connect(lambda: (not self._local_fs) and self._fade_out_gx())

        # Таймер опроса состояния видео
        self._poll = QTimer(self)
        self._poll.setInterval(500)
        self._poll.timeout.connect(self._poll_video_state)

        # Сигналы кнопок
        self.btn_close.clicked.connect(self._emit_closed)
        self.btn_back.clicked.connect(lambda: self._view and self._view.back())
        self.btn_fwd.clicked.connect(lambda: self._view and self._view.forward())
        self.btn_fs.clicked.connect(self._toggle_local_fullscreen)
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_mute.clicked.connect(self._toggle_mute)

        # Сигналы слайдера
        self.slider.sliderPressed.connect(self._on_seek_start)
        self.slider.sliderReleased.connect(self._on_seek_commit)
        self.slider.sliderMoved.connect(self._on_seek_preview)

        # Показать панель и запустить автоскрытие
        self._show_gx_temporarily()

        # Восстановить геометрию
        self._restore_settings()

    # ---------------- Публичное API ----------------
    def adopt_view(self, view: QWebEngineView):
        if not isinstance(view, QWebEngineView):
            return
        if self._view is view:
            return

        self.release_view()

        s = view.settings()
        if hasattr(QWebEngineSettings, "FullScreenSupportEnabled"):
            s.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)

        try:
            view.page().fullScreenRequested.connect(self._on_fullscreen_request)
        except Exception:
            pass

        try:
            view.loadFinished.connect(lambda ok: self._install_domain_guards(view))
            view.urlChanged.connect(lambda _u: self._install_domain_guards(view, delayed=True))
        except Exception:
            pass

        view.setParent(self._root)
        self._vbox.addWidget(view, 1)
        view.show()
        self._view = view

        # Начинаем опрос видео
        self._poll.start()

    def release_view(self):
        v = self._view
        if v is not None:
            try:
                v.page().fullScreenRequested.disconnect(self._on_fullscreen_request)
            except Exception:
                pass
            self._vbox.removeWidget(v)
            v.setParent(None)
            self._view = None
        self._poll.stop()
        return v

    # ---------------- Локальный fullscreen ----------------
    def _toggle_local_fullscreen(self):
        self._set_local_fs(not self._local_fs)

    def _set_local_fs(self, enable: bool):
        self._local_fs = enable
        self._gx.setVisible(not enable)
        if not enable:
            self._show_gx_temporarily()

    def _on_fullscreen_request(self, req):
        try:
            req.reject()
        except Exception:
            pass
        toggle_on = False
        try:
            toggle_on = bool(req.toggleOn())
        except Exception:
            pass
        self._set_local_fs(toggle_on)

    # ---------------- Инъекции CSS/JS (YouTube guard + контроллер) ----------------
    def _install_domain_guards(self, view: QWebEngineView, delayed=False):
        if delayed:
            QTimer.singleShot(250, lambda: self._install_domain_guards(view, delayed=False))
            return

        url = view.url().toString().lower()

        common_css = r"""
        html, body { width:100% !important; height:100% !important; overflow:hidden !important; }
        video, .html5-video-player, #movie_player, .ytp-player-content, .html5-video-container {
            width:100% !important; height:100% !important;
            max-width:100% !important; max-height:100% !important;
            position:absolute !important; top:0 !important; left:0 !important;
            object-fit:contain !important; background:#000 !important;
        }
        """
        js_inject_css = f"""
        (function(){{
            try {{
                var id='__pip_css_patch__';
                if(!document.getElementById(id)) {{
                    var st=document.createElement('style');
                    st.id=id; st.type='text/css';
                    st.appendChild(document.createTextNode({common_css!r}));
                    (document.head||document.documentElement).appendChild(st);
                }}
            }} catch(e){{}}
        }})();"""
        view.page().runJavaScript(js_inject_css)

        # Универсальная «панель управления» через window.__pip__ (по требованию)
        control_js = r"""
        (function(){
          try {
            if (window.__pip__) return;
            function $v(){
              return document.querySelector('video.html5-main-video') ||
                     document.querySelector('video') || null;
            }
            window.__pip__ = {
              exists: function(){ return !!$v(); },
              state: function(){
                var v=$v(); if(!v) return null;
                var dur = (isFinite(v.duration) && !isNaN(v.duration)) ? v.duration : 0;
                return { paused: v.paused, muted: v.muted, ct: v.currentTime||0, dur: dur, vol: v.volume };
              },
              togglePlay: function(){ var v=$v(); if(!v) return false; if(v.paused) v.play(); else v.pause(); return !v.paused; },
              toggleMute: function(){ var v=$v(); if(!v) return false; v.muted = !v.muted; return v.muted; },
              seekTo: function(t){ var v=$v(); if(!v) return false; try{ v.currentTime = Math.max(0, Math.min(v.duration||1e9, t)); }catch(e){}; return true; },
              seekBy: function(dt){ var v=$v(); if(!v) return false; try{ v.currentTime = Math.max(0, v.currentTime + dt); }catch(e){}; return true; },
              volumeBy: function(dv){ var v=$v(); if(!v) return false; v.volume = Math.max(0, Math.min(1, (v.volume||0) + dv)); return v.volume; }
            };
          } catch(e){}
        })();"""
        view.page().runJavaScript(control_js)

        if "youtube.com" in url or "youtu.be" in url:
            yt_js = r"""
            (function(){
              try {
                var v = document.querySelector('video.html5-main-video');
                if (v && !v.__pip_hooked) {
                  v.__pip_hooked = true;
                  v.addEventListener('dblclick', function(ev){ ev.preventDefault(); ev.stopPropagation(); }, true);
                }
                if (!window.__pip_key_hooked) {
                  window.__pip_key_hooked = true;
                  document.addEventListener('keydown', function(ev){
                    if (ev.key === 'f' || ev.key === 'F') { ev.preventDefault(); ev.stopPropagation(); }
                  }, true);
                }
                var root = document.querySelector('.html5-video-player');
                if (root) {
                  function stripFS(){ root.classList.remove('ytp-web-fullscreen','ytp-fullerscreen'); }
                  stripFS();
                  if (!root.__pip_observer) {
                    root.__pip_observer = new MutationObserver(stripFS);
                    root.__pip_observer.observe(root, { attributes:true, attributeFilter:['class'] });
                  }
                }
              } catch(e){}
            })();"""
            view.page().runJavaScript(yt_js)

    # ---------------- Анимации и позиционирование GX ----------------
    def _show_gx_temporarily(self):
        self._fade_in_gx()
        self._gx_timer.start(1600)

    def _position_gx(self):
        # панель снизу по центру, с полями
        margin = 12
        w = min(360, max(180, self.width() - margin * 2))
        self._gx.setFixedWidth(w)
        self._gx.move((self.width() - w) // 2, self.height() - self._gx.height() - margin)
        self._gx.raise_()

    def _fade_in_gx(self):
        self._gx.show()
        self._gx.raise_()
        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._gx_fx, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def _fade_out_gx(self):
        if self._anim and self._anim.state() == QPropertyAnimation.Running:
            self._anim.stop()
        self._anim = QPropertyAnimation(self._gx_fx, b"opacity", self)
        self._anim.setDuration(320)
        self._anim.setStartValue(self._gx_fx.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._gx.hide)
        self._anim.start()

    # ---------------- События окна ----------------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._position_gx()

    def enterEvent(self, e):
        self._show_gx_temporarily()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._local_fs:
            self._fade_out_gx()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._toggle_local_fullscreen()
        super().mouseDoubleClickEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPos()
            self._start_geom = self.geometry()
            self._resize_dir = self._hit_test(e.pos())
            self._resizing = self._resize_dir is not None

            clicked_widget = self.childAt(e.pos())
            if clicked_widget is self._gx:
                self._drag_started_in_gx = True
            elif clicked_widget is self._root:
                self._drag_started_in_gx = True
            else:
                self._drag_started_in_gx = False
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._resizing and self._drag_pos is not None:
            self._perform_resize(e.globalPos())
        elif self._drag_started_in_gx and self._drag_pos and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPos() - (self._drag_pos - self._start_geom.topLeft()))
        else:
            self.setCursor(self._cursor_for_dir(self._hit_test(e.pos())))
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._resizing = False
        self._resize_dir = None
        self._drag_pos = None
        self._drag_started_in_gx = False
        self.setCursor(Qt.ArrowCursor)
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key_Escape:
            self._emit_closed(); return
        if k == Qt.Key_Space:
            self._toggle_play(); return
        if k in (Qt.Key_M,):
            self._toggle_mute(); return
        if k in (Qt.Key_F,):
            self._toggle_local_fullscreen(); return
        if k == Qt.Key_Left:
            self._seek_by(-5.0); return
        if k == Qt.Key_Right:
            self._seek_by(+5.0); return
        if k == Qt.Key_Up:
            self._volume_by(+0.10); return
        if k == Qt.Key_Down:
            self._volume_by(-0.10); return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        try:
            self._save_settings()
            self._emit_closed()
        finally:
            super().closeEvent(e)

    # ---------------- Хелперы ресайза ----------------
    def _emit_closed(self): self.closed.emit()

    def _hit_test(self, pos):
        r = self.rect(); m = self.RESIZE_MARGIN
        left   = pos.x() <= m
        right  = pos.x() >= r.width()  - m
        top    = pos.y() <= m
        bottom = pos.y() >= r.height() - m
        if top and left:    return 'tl'
        if top and right:   return 'tr'
        if bottom and left: return 'bl'
        if bottom and right:return 'br'
        if left:            return 'l'
        if right:           return 'r'
        if top:             return 't'
        if bottom:          return 'b'
        return None

    def _cursor_for_dir(self, d):
        return {
            'tl': Qt.SizeFDiagCursor, 'br': Qt.SizeFDiagCursor,
            'tr': Qt.SizeBDiagCursor, 'bl': Qt.SizeBDiagCursor,
            'l':  Qt.SizeHorCursor,   'r':  Qt.SizeHorCursor,
            't':  Qt.SizeVerCursor,   'b':  Qt.SizeVerCursor,
            None: Qt.ArrowCursor
        }.get(d, Qt.ArrowCursor)

    def _perform_resize(self, gpos: QPoint):
        diff = gpos - self._drag_pos
        geom = self._start_geom
        L, T, R, B = geom.left(), geom.top(), geom.right(), geom.bottom()
        min_w, min_h = 280, 160
        d = self._resize_dir or ""
        if 'l' in d: L = min(R - min_w, L + diff.x())
        if 'r' in d: R = max(L + min_w, R + diff.x())
        if 't' in d: T = min(B - min_h, T + diff.y())
        if 'b' in d: B = max(T + min_h, B + diff.y())
        self.setGeometry(QRect(L, T, R - L, B - T))

    # ---------------- Сохранение настроек ----------------
    def _save_settings(self):
        st = QSettings("SalemExplorer", "PiP")
        st.setValue("geometry", self.saveGeometry())

    def _restore_settings(self):
        st = QSettings("SalemExplorer", "PiP")
        geo = st.value("geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception:
                pass

    # ---------------- Управление видео через JS ----------------
    def _js(self, code, cb=None):
        if not self._view:
            if cb: cb(None)
            return
        try:
            self._view.page().runJavaScript(code, cb)
        except Exception:
            if cb: cb(None)

    def _toggle_play(self):
        self._js("window.__pip__ && __pip__.togglePlay()", self._update_play_icon)

    def _toggle_mute(self):
        self._js("window.__pip__ && __pip__.toggleMute()", self._update_mute_icon)

    def _seek_by(self, dt):
        self._js(f"window.__pip__ && __pip__.seekBy({float(dt)})")

    def _seek_to(self, t):
        self._js(f"window.__pip__ && __pip__.seekTo({float(t)})")

    def _volume_by(self, dv):
        self._js(f"window.__pip__ && __pip__.volumeBy({float(dv)})")

    def _poll_video_state(self):
        # Получаем текущее состояние плеера раз в 0.5s
        self._js("window.__pip__ && __pip__.state()", self._apply_state)

    # ---------------- Таймлайн/лейблы ----------------
    @staticmethod
    def _fmt(t):
        try:
            t = int(t)
        except Exception:
            t = 0
        m, s = divmod(max(0, t), 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    def _apply_state(self, st):
        if not isinstance(st, dict):
            # нет видео — ставим дефолт
            self.btn_play.setText("▶")
            self.btn_mute.setText("🔇")
            self.lbl_time.setText("00:00 / 00:00")
            if not self._seeking:
                self.slider.setValue(0)
            self._last_duration = 0.0
            return

        paused = bool(st.get("paused", True))
        muted  = bool(st.get("muted", False))
        ct     = float(st.get("ct", 0.0) or 0.0)
        dur    = float(st.get("dur", 0.0) or 0.0)

        self.btn_play.setText("▶" if paused else "⏸")
        self.btn_mute.setText("🔇" if muted else "🔊")

        self.lbl_time.setText(f"{self._fmt(ct)} / {self._fmt(dur)}")
        self._last_duration = dur

        if not self._seeking and dur > 0:
            pos = int(1000 * (ct / max(dur, 0.001)))
            self.slider.blockSignals(True)
            self.slider.setValue(max(0, min(1000, pos)))
            self.slider.blockSignals(False)

    def _update_play_icon(self, _res=None):
        # Иконка уточнится в очередном _apply_state (периодическом опросе)
        pass

    def _update_mute_icon(self, _res=None):
        pass

    def _on_seek_start(self):
        self._seeking = True

    def _on_seek_preview(self, v):
        # Обновляем лейбл превью во время перетаскивания
        if self._last_duration > 0:
            ct = (v / 1000.0) * self._last_duration
            self.lbl_time.setText(f"{self._fmt(ct)} / {self._fmt(self._last_duration)}")

    def _on_seek_commit(self):
        v = self.slider.value()
        self._seeking = False
        if self._last_duration > 0:
            ct = (v / 1000.0) * self._last_duration
            self._seek_to(ct)

