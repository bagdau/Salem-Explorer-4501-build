/* ===========================
   Salem Explorer — main.js
   Устойчивый к Qt (без падений)
   =========================== */
/* --- Smooth Resize Guard (coalesce + marker) --- */
(function () {
  let raf = 0, endTimer = 0;

  function onResize() {
    const root = document.documentElement;
    // Ставим маркер, чтобы CSS отрубил эффекты
    if (!root.classList.contains('resizing')) root.classList.add('resizing');

    // Коалесцируем любые наши действия до кадра
    if (!raf) {
      raf = requestAnimationFrame(() => {
        raf = 0;
        // важно: никаких тяжёлых чтений стиля и синхронных layout здесь
      });
    }

    // Снимем маркер, когда пользователь «отпустил» окно
    clearTimeout(endTimer);
    endTimer = setTimeout(() => {
      root.classList.remove('resizing');
    }, 160);
  }

  // Лёгкий обработчик (passive), чтобы не блокировать поток
  window.addEventListener('resize', onResize, { passive: true });

  // Если кто-то уже назначил window.onresize — завернём его
  if (typeof window.onresize === 'function') {
    const prev = window.onresize;
    window.onresize = function () { onResize(); return prev.apply(this, arguments); };
  }
})();


"use strict";

/* ---------- ENV / SAFETY ---------- */
const Env = {
  isQt: (() => {
    const ua = (navigator.userAgent || "").toLowerCase();
    return ua.includes("qtwebengine") || ua.includes("salembrowser") || !!window.qt;
  })()
};

// Перехват "новых окон": в Qt без createWindow валится — форсим навигацию в этой вкладке
(function forceSameTabInQt(){
  if (!Env.isQt) return;

  // Любые <a target="_blank"> -> в текущую вкладку
  document.addEventListener("click", (e) => {
    const a = e.target.closest('a[target="_blank"], a[rel~="noopener"], a[rel~="noreferrer"]');
    if (a && a.href) {
      e.preventDefault();
      location.assign(a.href);
    }
  }, true);

  // Любые window.open(...) -> в этой вкладке
  const _open = window.open;
  window.open = function(url, target){
    if (url && (target === "_blank" || !target)) { location.assign(url); return null; }
    return _open.apply(window, arguments);
  };
})();

// Глобальный «предохранитель», чтобы не ронять скрипты
window.addEventListener("error", (e)=>console.error("[JS ERROR]", e?.message, e?.error));
window.addEventListener("unhandledrejection", (e)=>console.error("[JS UNHANDLED REJECTION]", e?.reason));

/* ---------- CONSTS / APPS ---------- */
const iconBaseUrl = "https://officialcorporationsalem.kz/iconsSalemBrowser/";
const CUSTOM_APPS_LS = "slm.sidebar.customApps";

/** Базовые (вшитые) приложения слева */
const builtinSidebarApps = [
  { title: "Почта",     icon: "gmail.png",     link: "https://mail.google.com/" },
  { title: "Новости",   icon: "news.png",      link: "https://tengrinews.kz" },
  { title: "Погода",    icon: "weather.png",   link: "https://officialcorporationsalem.kz/weather/index.html" },
  { title: "YouTube",   icon: "youtube.png",   link: "https://www.youtube.com" },
  { title: "Музыка",    icon: "music.png",     link: "http://127.0.0.1:7000/" },
  { title: "Календарь", icon: "calendar.png",  link: "https://officialcorporationsalem.kz/weather/salem_weather.php" },
  { title: "Настройки", icon: "settings.png",  action: () => openSettings() }
];

/* ---------- THEME ---------- */
const THEMES = ["dark", "light", "system"];
let themeIndex = 0;

function getSavedTheme(){ return localStorage.getItem("salem_theme") || "dark"; }

function applyTheme(theme){
  document.body.classList.remove("dark","light","system");
  if (theme === "system"){
    const prefersDark = matchMedia("(prefers-color-scheme: dark)").matches;
    document.body.classList.add(prefersDark ? "dark" : "light");
  } else {
    document.body.classList.add(theme);
  }
  const label = theme === "dark" ? "Dark" : theme === "light" ? "Light" : "Auto";
  const el = document.getElementById("themeStatus");
  if (el) el.textContent = label;
}

function toggleTheme(){
  themeIndex = (themeIndex + 1) % THEMES.length;
  const newTheme = THEMES[themeIndex];
  localStorage.setItem("salem_theme", newTheme);
  applyTheme(newTheme);
}
window.toggleTheme = toggleTheme;

/* ---------- SIDEBAR: данные ---------- */
function loadCustomApps(){
  try { return JSON.parse(localStorage.getItem(CUSTOM_APPS_LS) || "[]"); }
  catch { return []; }
}
function saveCustomApps(arr){
  try { localStorage.setItem(CUSTOM_APPS_LS, JSON.stringify(arr)); } catch {}
}
function isValidUrl(u){
  try { new URL(u, location.origin); return true; } catch { return false; }
}
function getSidebarApps(){
  return [...builtinSidebarApps, ...loadCustomApps()];
}

/* ---------- SIDEBAR: рендер ---------- */
function renderSidebarApps(){
  const sidebar = document.getElementById('sidebar-apps') || document.querySelector('.sidebar-apps');
  if (!sidebar) return;
  sidebar.innerHTML = '';

  getSidebarApps().forEach(app => {
    const isAction = typeof app.action === "function";
    const el = isAction ? document.createElement('button') : document.createElement('a');
    el.className = 'sidebar-icon';
    el.title = app.title;

    if (!isAction && app.link){
      el.href = app.link;
      // Позволяем открывать в новой вкладке в обычных браузерах;
      // в Qt перехватим выше и уйдём в текущую вкладку — без падения.
      el.target = "_blank";
      el.rel = "noopener";
    }

    const img = document.createElement('img');
    img.src = (app.icon && (app.icon.startsWith("http://") || app.icon.startsWith("https://"))) ? app.icon : (iconBaseUrl + app.icon);
    img.alt = app.title;
    img.draggable = false;
    el.appendChild(img);

    if (isAction){
      el.type = "button";
      el.addEventListener('click', app.action);
    }
    sidebar.appendChild(el);
  });
}

/* ---------- DELGATES / UX ---------- */
function attachSidebarDelegates(){
  const hoverSound = document.getElementById("hoverSound");
  let hoverTimer = 0;

  // Звук наведения (троттлинг, чтобы не трещал)
  document.addEventListener("mouseover", (e)=>{
    const btn = e.target.closest(".sidebar-icon, .icon-btn");
    if (!btn || !hoverSound) return;
    const now = performance.now();
    if (now - hoverTimer < 60) return;
    hoverTimer = now;
    try { hoverSound.currentTime = 0; hoverSound.play(); } catch(_) {}
  });

  // Открытие настроек по иконке/кнопке меню
  document.addEventListener('click', (e)=>{
    const openBtn = e.target.closest('.sidebar-icon[title="Настройки"], .menu-btn');
    if (openBtn){ e.stopPropagation(); openSettings(); }
  });
}

/* ---------- SETTINGS PANEL ---------- */
function openSettings(){
  const overlay  = document.getElementById('settingsOverlay');
  const settings = document.getElementById('settingsContainer');
  if (!overlay || !settings) return;
  settings.style.right = "0";
  overlay.classList.add('active');
}
function closeSettings(){
  const overlay  = document.getElementById('settingsOverlay');
  const settings = document.getElementById('settingsContainer');
  if (!overlay || !settings) return;
  settings.style.right = "-400px";
  overlay.classList.remove('active');
}
window.openSettings  = openSettings;
window.closeSettings = closeSettings;

function bindSettingsClose(){
  const overlay  = document.getElementById('settingsOverlay');
  const settings = document.getElementById('settingsContainer');
  const closeBtn = document.querySelector('.settings-close-btn');
  if (overlay) overlay.onclick = () => closeSettings();
  if (closeBtn) closeBtn.onclick = (e)=>{ e.stopPropagation(); closeSettings(); };
  if (settings) settings.onclick = (e)=> e.stopPropagation();
  closeSettings();
}

/* ---------- MINI PROFILE POPOVER ---------- */
(function initProfilePopover(){
  const profileBtn = document.getElementById('profile-btn');
  const profilePopup = document.getElementById('profile-popup');
  let profileOpen = false;

  if (profileBtn && profilePopup){
    profileBtn.onclick = function(e){
      e.stopPropagation();
      profilePopup.classList.toggle('active');
      profileOpen = profilePopup.classList.contains('active');
    };
    document.addEventListener('click', function(e){
      if (profileOpen && !profilePopup.contains(e.target) && !profileBtn.contains(e.target)) {
        profilePopup.classList.remove('active'); profileOpen = false;
      }
    });
  }
})();

/* ---------- PROFILE (тихий режим) ---------- */
const PROFILE_API = '/api/profile.php'; // если нет роутов — останутся заглушки

function cacheBust(url){
  try {
    const u = new URL(url, location.origin);
    u.searchParams.set('v', Date.now().toString());
    return u.href; // ВАЖНО: не u.pathname
  } catch {
    return url + (url.includes('?') ? '&' : '?') + 'v=' + Date.now();
  }
}
async function fetchProfile(){
  try{
    const res = await fetch(PROFILE_API, { credentials: 'include', headers: {Accept:'application/json'} });
    if (!res.ok) return null;
    return await res.json();
  }catch{ return null; }
}
function applyProfile(p){
  if (!p) return;
  const rec = p.profile ? p.profile : p; // поддержка формата {profile:{...}}
  const name  = rec.name  || rec.full_name || '';
  const email = rec.email || '';
  // Ставим живой дефолт (он у тебя точно есть и отдаётся 200)
  const avatar = rec.avatar || rec.avatar_url || '/static/img/Salem.png';

  const imgBig  = document.getElementById('profile-avatar-img');
  const imgMini = document.getElementById('profile-avatar-mini');
  const nEl = document.querySelector('#profile-popup .profile-name');
  const eEl = document.querySelector('#profile-popup .profile-email');

  if (imgBig)  imgBig.src  = cacheBust(avatar);
  if (imgMini) imgMini.src = cacheBust(avatar);
  if (nEl) nEl.textContent = name || 'Қонақ';
  if (eEl) eEl.textContent = email || '';
}
async function initProfileArea(){
  const p = await fetchProfile();
  if (p && !p.error) applyProfile(p);
}

// Live-обновления из других вкладок (если есть BroadcastChannel)
(function bindProfileChannel(){
  try {
    const bc = new BroadcastChannel('salem_profile');
    bc.onmessage = (ev)=>{
      const data = ev.data || {};
      if (data?.type === 'profile-updated'){
        applyProfile(data.profile || {});
      } else if (data?.type === 'avatar-changed'){
        const p = { avatar: data.url, name: data.name, email: data.email };
        applyProfile(p);
      }
    };
  } catch(_) {}
})();

/* ---------- SEARCH ---------- */
function bindSearch(){
  const input = document.getElementById('search-input');
  const btn   = document.getElementById('search-button');
  if (!input || !btn) return;

  function go(){
    const q = (input.value || "").trim();
    if (!q) return;
    const url = "https://www.google.com/search?q=" + encodeURIComponent(q);
    // В обычном браузере новая вкладка; в Qt — уйдём в текущую (см. перехват выше)
    window.open(url, "_blank", "noopener");
  }
  btn.addEventListener('click', go);
  input.addEventListener('keydown', (e)=>{ if (e.key === 'Enter') go(); });
}

/* ---------- ADD APP MODAL ---------- */
function openAddModal(){
  const m = document.getElementById('addModal');
  if (m) { m.style.display = 'flex'; }
}
function closeAddModal(){ const m = document.getElementById('addModal'); if (m) m.style.display = 'none'; }
window.closeAddModal = closeAddModal;

function addCustomApp(){
  const nameEl = document.getElementById('newAppName');
  const urlEl  = document.getElementById('newAppUrl');
  const iconEl = document.getElementById('newAppIcon');

  const name = (nameEl?.value || "").trim();
  const link = (urlEl?.value || "").trim();
  const icon = (iconEl?.value || "").trim();

  if (!name || !link || !isValidUrl(link)){
    alert("Толтырыңыз: атауы және дұрыс сілтеме (URL).");
    return;
  }
  const custom = loadCustomApps();
  custom.push({ title: name, icon: icon || (iconBaseUrl + "link.png"), link });
  saveCustomApps(custom);
  renderSidebarApps();
  closeAddModal();
}
window.addCustomApp = addCustomApp;

/* ---------- BOOT ---------- */
window.addEventListener("DOMContentLoaded", () => {
  // Тема
  const saved = getSavedTheme();
  themeIndex = THEMES.indexOf(saved); if (themeIndex === -1) themeIndex = 0;
  applyTheme(saved);

  // Сайдбар и делегаты
  renderSidebarApps();
  attachSidebarDelegates();
  bindSettingsClose();

  // Профиль (необязателен)
  initProfileArea();

  // Поиск
  bindSearch();

  // Модалка «Добавить»
  const addBtn = document.getElementById("addButton");
  if (addBtn) addBtn.addEventListener('click', openAddModal);
});
