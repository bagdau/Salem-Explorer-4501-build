// YouTube: «перепрыгиваем» рекламу — аккуратно и без хака сети.
// Идея: как только у .html5-video-player появляется класс .ad-showing,
// глушим звук, ускоряем видеотрек, жмём «Пропустить». Потом возвращаем.

(() => {
  if (!/\.youtube\.com$/.test(location.hostname)) return;

  let original = { muted: null, rate: null };
  let skipping = false;

  const getPlayer = () => document.querySelector("video.html5-main-video");
  const getRoot = () => document.querySelector(".html5-video-player");

  function isAdShowing() {
    const root = getRoot();
    return root?.classList?.contains("ad-showing");
  }

  function trySkipButton() {
    const btn =
      document.querySelector(".ytp-ad-skip-button") ||
      document.querySelector(".ytp-ad-skip-button-modern");
    if (btn) btn.click();
  }

  function enterAdSkip() {
    if (skipping) return;
    const v = getPlayer();
    if (!v) return;

    skipping = true;

    // Сохраняем
    if (original.muted === null) original.muted = v.muted;
    if (original.rate === null) original.rate = v.playbackRate;

    // Ускоряем и глушим
    v.muted = true;
    try { v.playbackRate = 16; } catch {}

    // Пытаемся жать «Пропустить» как можно чаще
    const clicker = setInterval(trySkipButton, 150);

    // как только реклама уйдёт — откат
    const endCheck = setInterval(() => {
      if (!isAdShowing()) {
        clearInterval(clicker);
        clearInterval(endCheck);
        exitAdSkip();
      }
    }, 200);
  }

  function exitAdSkip() {
    const v = getPlayer();
    if (v) {
      try { v.playbackRate = original.rate ?? 1; } catch {}
      v.muted = original.muted ?? false;
    }
    original = { muted: null, rate: null };
    skipping = false;
  }

  // Наблюдаем за сменой состояния
  const obs = new MutationObserver(() => {
    if (isAdShowing()) enterAdSkip();
  });

  const start = () => {
    const root = getRoot();
    if (!root) return;
    obs.observe(root, { attributes: true, attributeFilter: ["class"] });
    if (isAdShowing()) enterAdSkip();
  };

  // YouTube SPA → ждём корневой плеер
  const awaiter = new MutationObserver(() => {
    if (getRoot()) {
      awaiter.disconnect();
      start();
    }
  });
  awaiter.observe(document.documentElement, { childList: true, subtree: true });

  // Мелкие баннеры и оверлеи:
  const style = document.createElement("style");
  style.textContent = `
    .ytp-ad-player-overlay, .ytp-ad-overlay-slot, .ytp-ad-image-overlay,
    #player-ads, .video-ads, ytd-action-companion-ad-renderer, tp-yt-paper-dialog.ytd-popup-container {
      display: none !important;
    }
  `;
  document.documentElement.appendChild(style);
})();
