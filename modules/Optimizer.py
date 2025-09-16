# Optimizer.py
import os, gc, psutil, traceback
from PyQt5.QtCore import QTimer
from PyQt5.QtWebEngineWidgets import QWebEnginePage
import time

class ResourceOptimizer:
    def __init__(self, browser, profile=None,
                 interval_ms=25_000,
                 cpu_limit=65,
                 ram_limit=80,
                 discard_aggressive=False,
                 cache_cleanup_each=8,
                 debug=False):
        self.browser = browser
        self.profile = profile
        self.cpu_limit = int(cpu_limit)
        self.ram_limit = int(ram_limit)
        self.discard_aggressive = bool(discard_aggressive)
        self.cache_cleanup_each = max(0, int(cache_cleanup_each))
        self.debug = bool(debug)

        self._has_lifecycle = hasattr(QWebEnginePage, "Discarded")
        self._tick = 0
        self._last_gc = 0

        self._timer = QTimer()
        self._timer.timeout.connect(self._optimize)
        self._timer.start(int(interval_ms))

    def on_tab_activated(self, index: int):
        """Размораживаем активную вкладку при переключении."""
        try:
            w = self.browser.tabs.widget(index)
            if not hasattr(w, "page"):
                return
            p = w.page()
            if hasattr(QWebEnginePage, "Discarded"):
                try:
                    p.setLifecycleState(QWebEnginePage.Active)
                except Exception:
                    pass
            try:
                p.setAudioMuted(False)
            except Exception:
                pass
        except Exception:
            if self.debug:
                traceback.print_exc()


    def _optimize(self):
        try:
            self._tick += 1
            cpu = psutil.cpu_percent(interval=0.1)  # сглаживание
            ram = psutil.virtual_memory().percent
            pressure = (cpu > self.cpu_limit) or (ram > self.ram_limit)

            if self.debug:
                print(f"[Optimizer] tick={self._tick} cpu={cpu:.1f}% ram={ram:.1f}% pressure={pressure}")

            # 1. Оптимизация вкладок
            for i in range(self.browser.tabs.count()):
                if i == self.browser.tabs.currentIndex():
                    continue
                w = self.browser.tabs.widget(i)
                if not hasattr(w, "page"):
                    continue
                p = w.page()

                try: p.setAudioMuted(True)
                except: pass

                if self._has_lifecycle and (pressure or self.discard_aggressive):
                    try:
                        p.setLifecycleState(QWebEnginePage.Discarded)
                        if self.debug: print(f"[Optimizer] discard → tab {i}")
                        bar = getattr(self.browser.tabs, "tabBar", lambda: None)()
                        if hasattr(bar, "set_tab_badge"):
                            bar.set_tab_badge(i, "⏸")
                    except: pass
                elif pressure:
                    try:
                        p.triggerAction(QWebEnginePage.Stop)
                        p.runJavaScript("""
                          try {
                            document.querySelectorAll('video,audio')
                                    .forEach(m => { try{m.pause()}catch(_){}} )
                          } catch(_) {}
                        """)
                        if self.debug: print(f"[Optimizer] soft-pause → tab {i}")
                    except: pass

            # 2. Чистка кэша
            if self.profile and self.cache_cleanup_each and (self._tick % self.cache_cleanup_each == 0):
                try:
                    self.profile.clearHttpCache()
                    if self.debug: print("[Optimizer] clearHttpCache()")
                except: pass

            # 3. GC ограничить по времени (не чаще 30 сек)
            if pressure and (time.time() - self._last_gc > 30):
                gc.collect()
                self._last_gc = time.time()
                if self.debug: print("[Optimizer] gc.collect()")

            # 4. Адаптивный интервал (бонус)
            new_interval = 15_000 if pressure else 30_000
            if self._timer.interval() != new_interval:
                self._timer.setInterval(new_interval)

        except Exception:
            if self.debug:
                traceback.print_exc()
