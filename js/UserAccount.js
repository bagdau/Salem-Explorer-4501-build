// UserAccount.js — стабильные вкладки, модалка ошибок, генератор паролей, сейф логинов, редирект с лоадером.
(function () {
  'use strict';

  // ---------- helpers
  const $ = (sel, r = document) => r.querySelector(sel);
  const $$ = (sel, r = document) => Array.from(r.querySelectorAll(sel));

  // ---------- Toast (мини-уведомление)
  let toast = $('#toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  function showToast(msg) {
    toast.textContent = msg;
    toast.classList.add('show');
    setTimeout(() => toast.classList.remove('show'), 1800);
  }

  // ---------- Modal (для ошибок)
  let modal = $('#modal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'modal';
    modal.className = 'modal';
    modal.setAttribute('aria-hidden','true');
    modal.innerHTML = `
      <div class="modal-card" role="document">
        <div class="modal-title" id="modalTitle">Сообщение</div>
        <div class="modal-body" id="modalBody"></div>
        <div class="modal-actions">
          <button class="btn secondary tiny" id="modalClose">Закрыть</button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }
  const modalTitle = $('#modalTitle', modal);
  const modalBody  = $('#modalBody', modal);
  const modalClose = $('#modalClose', modal);

  function showModalError(msg, title='Ошибка') {
    modalTitle.textContent = title;
    modalBody.textContent  = msg;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden','false');
    modalClose && modalClose.focus();
  }
  function hideModal() {
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden','true');
  }
  modalClose && modalClose.addEventListener('click', hideModal);
  modal.addEventListener('click', (e)=>{ if (e.target === modal) hideModal(); });
  document.addEventListener('keydown', (e)=>{ if (e.key === 'Escape' && modal.classList.contains('show')) hideModal(); });

  // ---------- Loader overlay (редирект)
  let overlay = $('#loaderOverlay');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'loaderOverlay';
    overlay.className = 'overlay';
    overlay.setAttribute('aria-hidden','true');
    overlay.innerHTML = `
      <div class="loader">
        <div class="spinner" aria-hidden="true"></div>
        <div class="hint">Загружаем профиль…</div>
      </div>`;
    document.body.appendChild(overlay);
  }
  function showLoaderAndRedirect(url) {
    overlay.classList.add('show');
    overlay.setAttribute('aria-hidden','false');
    setTimeout(()=> { window.location.href = url; }, 1800);
  }

  // ---------- Tabs (устойчивое переключение)
  const tabs   = $$('.tabs .tab');
  const panels = $$('.panel');
  const tablist = $('.tabs');

  function selectTabByButton(btn) {
    if (!btn) return;
    const targetId = btn.getAttribute('aria-controls'); // panel-*
    const target = document.getElementById(targetId);
    tabs.forEach(t => t.setAttribute('aria-selected', String(t === btn)));
    panels.forEach(p => p.setAttribute('aria-hidden', String(p !== target)));
  }
  // клики
  tabs.forEach(btn => btn.addEventListener('click', () => selectTabByButton(btn)));
  // клавиатура
  if (tablist) {
    tablist.addEventListener('keydown', (e) => {
      const i = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        e.preventDefault();
        const dir = e.key === 'ArrowRight' ? 1 : -1;
        const next = tabs[(i + dir + tabs.length) % tabs.length];
        next.focus(); selectTabByButton(next);
      }
      if (e.key === 'Home') { e.preventDefault(); tabs[0].focus(); selectTabByButton(tabs[0]); }
      if (e.key === 'End')  { e.preventDefault(); const last = tabs[tabs.length-1]; last.focus(); selectTabByButton(last); }
    });
  }
  // инициализация — используем отмеченную или «Вход»
  const initBtn = tabs.find(t => t.getAttribute('aria-selected') === 'true') || $('#tab-login') || tabs[0];
  selectTabByButton(initBtn);

  // ---------- Показ/скрытие пароля
  $$('[data-toggle="password"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-target');
      const input = document.getElementById(id);
      if (!input) return;
      const isPwd = input.type === 'password';
      input.type = isPwd ? 'text' : 'password';
      btn.textContent = isPwd ? '🙈' : '👁️';
      btn.setAttribute('aria-label', isPwd ? 'Скрыть пароль' : 'Показать пароль');
    });
  });

  // ---------- Индикатор силы пароля
  const pw = $('#signup-password');
  const pwBar = $('#pwStrength');
  const pwHint = $('#pwHint');
  function zxcv(s){
    if(!s) return 0;
    const checks = [ s.length >= 8, /[a-z]/.test(s) && /[A-Z]/.test(s), /\d/.test(s), /[^\w\s]/.test(s), s.length >= 12 ];
    return checks.reduce((a,b)=> a + (b?1:0), 0); // 0..5
  }
  function renderStrength(n){
    if (!pwBar || !pwHint) return;
    const pct = [0,25,45,70,85,100][n];
    pwBar.style.width = pct + '%';
    const colors = ['var(--line)','var(--err)','var(--warn)','var(--warn)','var(--ok)','var(--ok)'];
    pwBar.style.background = colors[n];
    const titles = ['—','слабый','слабоват','средний','хороший','сильный'];
    pwHint.textContent = 'Надёжность: ' + titles[n];
  }
  pw && pw.addEventListener('input', ()=> renderStrength(zxcv(pw.value)));
  renderStrength(0);

  // ---------- OTP автопереход
  const otpInputs = $$('.otp input');
  otpInputs.forEach((el, idx)=>{
    el.addEventListener('input', (e)=>{
      e.target.value = e.target.value.replace(/\D/g,'').slice(0,1);
      if(e.target.value && idx < otpInputs.length-1) otpInputs[idx+1].focus();
    });
    el.addEventListener('keydown',(e)=>{ if(e.key==='Backspace' && !e.target.value && idx>0) otpInputs[idx-1].focus(); });
  });
  const otpBox = $('#otp');
  otpBox && otpBox.addEventListener('paste', (e)=>{
    const text=(e.clipboardData || window.clipboardData).getData('text').replace(/\D/g,'');
    if(text.length>=otpInputs.length){
      e.preventDefault();
      text.slice(0,otpInputs.length).split('').forEach((ch,i)=> otpInputs[i].value = ch);
      otpInputs[otpInputs.length-1].focus();
    }
  });

  // ---------- Хранилище: Qt WebChannel → ./UserData/userLogin.json; фолбэк — localStorage
  let SalemBridge = null;
  function initChannel(){
    if (window.qt && qt.webChannelTransport && typeof QWebChannel !== 'undefined') {
      new QWebChannel(qt.webChannelTransport, function(channel) {
        SalemBridge = channel.objects.SalemBridge || null;
        renderStatus();
      });
    } else {
      renderStatus();
    }
  }
  // инициализация канала после загрузки DOM
  if (document.readyState === 'complete') initChannel();
  else window.addEventListener('load', initChannel);

  const storeKey = 'salem.account.vault'; // массив аккаунтов

  async function readRaw(){
    if (SalemBridge && SalemBridge.getUser){
      return new Promise(resolve => SalemBridge.getUser(s => resolve(s || '')));
    }
    return localStorage.getItem(storeKey) || localStorage.getItem('salem.account.demo') || '';
  }
  async function writeRaw(jsonStr){
    if (SalemBridge && SalemBridge.saveUser){
      return new Promise(resolve => SalemBridge.saveUser(jsonStr, ok => resolve(!!ok)));
    }
    localStorage.setItem(storeKey, jsonStr);
    return true;
  }
  async function getVault(){
    try {
      const raw = await readRaw();
      if (!raw) return [];
      const data = JSON.parse(raw);
      if (Array.isArray(data)) return data;
      if (data && typeof data === 'object') return [data]; // миграция со старого формата
      return [];
    } catch { return []; }
  }
  async function saveToVault(cred){
    const list = await getVault();
    const idx = list.findIndex(x => (x.email && x.email === cred.email) || (x.username && x.username === cred.username));
    if (idx >= 0) list[idx] = { ...list[idx], ...cred, updatedAt: new Date().toISOString() };
    else list.push({ ...cred, createdAt: new Date().toISOString() });
    const ok = await writeRaw(JSON.stringify(list, null, 2));
    if (ok) renderVault(list);
    return ok;
  }

  // ---------- Генератор пароля + копирование
  const btnGen  = $('#btnGen');
  const btnCopy = $('#btnCopy');
  function genPassword(len){
    const L = Math.max(8, Math.min(40, Number(len) || 14));
    const lowers = 'abcdefghijklmnopqrstuvwxyz';
    const uppers = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const digits = '0123456789';
    const symbols = '!@#$%^&*()-_=+[]{};:,.?';
    const all = lowers + uppers + digits + symbols;
    let out = '';
    out += lowers[Math.floor(Math.random()*lowers.length)];
    out += uppers[Math.floor(Math.random()*uppers.length)];
    out += digits[Math.floor(Math.random()*digits.length)];
    out += symbols[Math.floor(Math.random()*symbols.length)];
    for(let i=4;i<L;i++){ out += all[Math.floor(Math.random()*all.length)]; }
    // Перемешаем (Фишер-Йетс)
    out = out.split('');
    for(let i=out.length-1;i>0;i--){ const j=Math.floor(Math.random()*(i+1)); [out[i],out[j]]=[out[j],out[i]]; }
    return out.join('');
  }
  btnGen && btnGen.addEventListener('click', ()=>{
    const len = ($('#pwLen') ? $('#pwLen').value : 14);
    const val = genPassword(len);
    const p1 = $('#signup-password'); const p2 = $('#signup-password2');
    if (p1) p1.value = val; if (p2) p2.value = val;
    p1 && p1.dispatchEvent(new Event('input'));
    showToast('Сгенерирован сильный пароль');
  });
  btnCopy && btnCopy.addEventListener('click', async ()=>{
    const val = ($('#signup-password') || {}).value || '';
    try { await navigator.clipboard.writeText(val); showToast('Пароль скопирован'); }
    catch { showModalError('Не удалось скопировать пароль в буфер обмена.'); }
  });

  // ---------- Рендер «Паролей» + временное раскрытие
  const vaultBody = $('#vaultBody');
  function maskLogin(v){ if (!v) return '—'; const s=String(v); return s.length<=4?'••••':s.slice(0,2)+'••••'+s.slice(-2); }
  function maskEmail(e){
    if (!e) return '—';
    const [name, domain] = String(e).split('@');
    if (!domain) return maskLogin(e);
    const dn = domain.split('.'); const dmain = dn[0]||''; const tld = dn.slice(1).join('.')||'';
    const nameMasked = name.length<=2?'••':name.slice(0,2)+'••';
    const domMasked  = dmain.length<=2?'••':dmain.slice(0,2)+'••';
    return nameMasked+'@'+domMasked+(tld?'.'+tld:'');
  }
  function maskPassword(p){ return p ? '••••••••' : '—'; }
  function rowTemplate(u, idx){
    const loginMasked = maskLogin(u.username||'');
    const emailMasked = maskEmail(u.email||'');
    const passMasked  = maskPassword(u.password||'');
    const esc = s => String(s||'').replace(/"/g,'&quot;');
    return `
      <tr data-idx="${idx}">
        <td class="mono">${(u.first||'') + (u.last?' '+u.last:'')}</td>
        <td><span class="mono masked" data-kind="login" data-full="${esc(u.username)}" data-masked="${loginMasked}">${loginMasked}</span></td>
        <td><span class="mono masked" data-kind="email" data-full="${esc(u.email)}" data-masked="${emailMasked}">${emailMasked}</span></td>
        <td><span class="mono masked" data-kind="password" data-full="${esc(u.password)}" data-masked="${passMasked}">${passMasked}</span></td>
        <td class="tools"><button class="btn secondary tiny reveal" type="button">Раскрыть</button></td>
      </tr>`;
  }
  function renderVault(list){
    if (!vaultBody) return;
    vaultBody.innerHTML = Array.isArray(list) ? list.map((u,i)=>rowTemplate(u,i)).join('') : '';
  }
  const activeTimers = new Map();
  vaultBody && vaultBody.addEventListener('click', (e)=>{
    const btn = e.target.closest('.reveal'); if (!btn) return;
    const tr = btn.closest('tr'); if (!tr) return;
    const idx = tr.getAttribute('data-idx');
    const spans = tr.querySelectorAll('.masked');
    if (activeTimers.has(idx)) return;

    spans.forEach(s => s.textContent = s.getAttribute('data-full') || '—');
    btn.disabled = true; let secs = 6; const original = btn.textContent; btn.textContent = 'Раскрыто (6с)';
    const t = setInterval(()=>{
      secs -= 1;
      if (secs > 0) { btn.textContent = `Раскрыто (${secs}с)`; }
      else {
        clearInterval(t);
        spans.forEach(s => s.textContent = s.getAttribute('data-masked'));
        btn.textContent = original; btn.disabled = false; activeTimers.delete(idx);
      }
    }, 1000);
    activeTimers.set(idx, t);
  });

  // ---------- Сабмит логина — ошибки в модалку, успех → редирект
  const loginForm = $('#loginForm');
  loginForm && loginForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const emailOrUser = ($('#login-email') || {}).value?.trim() || '';
    const password    = ($('#login-password') || {}).value || '';

    if (!emailOrUser || !password) {
      showModalError('Заполните логин/email и пароль.', 'Недостаточно данных');
      return;
    }
    const list = await getVault();
    const user = list.find(u => u.email === emailOrUser || u.username === emailOrUser);
    if (!user) { showModalError('Пользователь с таким логином/email не найден.', 'Ошибка входа'); return; }
    if (user.password !== password) { showModalError('Пароль неверный. Проверьте раскладку и Caps Lock.', 'Ошибка входа'); return; }

    // успех
    showToast('Вход выполнен');
    user.lastUsedAt = new Date().toISOString();
    await writeRaw(JSON.stringify(list, null, 2));
    renderVault(list);
    showLoaderAndRedirect('https://officialcorporationsalem.kz/Salem.org.html');
  });

  // ---------- Сабмит регистрации — сохранение и переход на вкладку «Вход»
  const signupForm = $('#signupForm');
  signupForm && signupForm.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const u = {
      first: ($('#first-name')||{}).value?.trim() || '',
      last:  ($('#last-name')||{}).value?.trim()  || '',
      username: ($('#signup-username')||{}).value?.trim() || '',
      email:    ($('#signup-email')||{}).value?.trim()    || '',
      password: ($('#signup-password')||{}).value || ''
    };
    const p2 = ($('#signup-password2')||{}).value || '';
    const terms = ($('#terms')||{}).checked;

    if (!terms) { showModalError('Для регистрации примите условия использования.', 'Требуется согласие'); return; }
    if (!u.username || !u.email) { showModalError('Укажите логин и email.', 'Недостаточно данных'); return; }
    if (u.password !== p2) { showModalError('Пароли не совпадают.', 'Проверка пароля'); return; }
    if (zxcv(u.password) < 3) { showModalError('Пароль слабый. Усильте комбинацию (длина, регистры, цифры, символы).', 'Проверка пароля'); return; }

    const ok = await saveToVault(u);
    if (!ok) { showModalError('Не удалось сохранить учётную запись.', 'Ошибка сохранения'); return; }

    showToast('Логин и пароль сохранены');
    selectTabByButton($('#tab-login'));
    const loginEmail = $('#login-email');
    if (loginEmail) loginEmail.value = u.email;
    ($('#login-password')||{}).focus?.();
  });

  // ---------- Статус/тема
  const badge = $('#statusBadge');
  function renderStatus(){
    if (!badge) return;
    badge.textContent = (SalemBridge ? 'JSON-файл' : (navigator.onLine ? 'Онлайн' : 'Оффлайн'));
  }
  window.addEventListener('online', renderStatus);
  window.addEventListener('offline', renderStatus);
  const prefers = window.matchMedia('(prefers-color-scheme: dark)');
  document.documentElement.setAttribute('data-theme', prefers.matches ? 'dark' : 'light');
  prefers.addEventListener('change', (e)=>{ document.documentElement.setAttribute('data-theme', e.matches ? 'dark' : 'light'); });

  // ---------- Инициализация
  (async function init(){
    renderStatus();
    const list = await getVault();
    renderVault(list);
    const u0 = list && list[0];
    if (u0 && u0.email) { const el = $('#login-email'); if (el) el.value = u0.email; }
    // включим autocomplete на всякий случай
    $$('form').forEach(f => f.setAttribute('autocomplete','on'));
  })();

})();