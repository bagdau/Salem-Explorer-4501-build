/* account.js — adapted to Account.html (kk/ru) structure
 * Works with sections: #login-section, #register-section, #profile-section
 * Forms: #login-form, #register-form, #profile-form
 * Avatar: #avatar-upload (input[type=file]), #profile-avatar (img)
 * Buttons/links: .logout-btn, #theme-toggle, #mailto-link
 * Uses PHP API under /api/
 */
(function(){
  'use strict';

  const API_BASE = '/api/';
  const TIMEOUT  = 12000;
  const STORE_KEY = 'sx.profile';

  const $  = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  // -------- Theme toggle (Auto/Dark/Light cycle is optional; here simple toggle) --------
  (function themeInit(){
    const btn = $('#theme-toggle');
    const KEY = 'sx.theme';
    const apply = (mode)=>{
      document.body.classList.toggle('light', mode === 'light');
      document.body.classList.toggle('dark',  mode === 'dark');
    };
    let saved = localStorage.getItem(KEY) || 'auto';
    const prefersDark = matchMedia('(prefers-color-scheme: dark)');
    const sync = ()=> apply(saved === 'auto' ? (prefersDark.matches ? 'dark' : 'light') : saved);
    sync();
    prefersDark.addEventListener?.('change', sync);
    btn?.addEventListener('click', ()=>{
      saved = saved === 'auto' ? 'dark' : saved === 'dark' ? 'light' : 'auto';
      localStorage.setItem(KEY, saved);
      sync();
      btn.textContent = saved === 'auto' ? '◌' : saved === 'dark' ? '◌' : '◌';
      btn.setAttribute('title', 'Тема: ' + (saved === 'auto' ? 'Auto' : saved === 'dark' ? 'Dark' : 'Light'));
    });
    if (btn) { btn.textContent = saved === 'auto' ? '◌' : saved === 'dark' ? '●' : '●'; }
  })();

  // -------- Toasts --------
  const toastHost = document.createElement('div');
  toastHost.className = 'sx-toast-host';
  document.addEventListener('DOMContentLoaded', ()=> document.body.appendChild(toastHost));
  function showToast(msg, type='info', ms=2200){
    const el = document.createElement('div');
    el.className = `sx-toast sx-toast--${type}`;
    el.textContent = String(msg||'');
    toastHost.appendChild(el);
    requestAnimationFrame(()=> el.classList.add('show'));
    setTimeout(()=>{ el.classList.remove('show'); setTimeout(()=> el.remove(), 220); }, ms);
  }

  // -------- Modal for errors --------
  let modal, modalTitle, modalMsg;
  function ensureModal(){
    if (modal) return;
    modal = document.createElement('div');
    modal.className = 'sx-modal';
    modal.innerHTML = `
      <div class="sx-modal__backdrop"></div>
      <div class="sx-modal__dialog" role="dialog" aria-modal="true">
        <div class="sx-modal__head">
          <h3 class="sx-modal__title">Хабарлама</h3>
          <button class="sx-modal__x" type="button" aria-label="Жабу">×</button>
        </div>
        <div class="sx-modal__body"></div>
        <div class="sx-modal__foot">
          <button class="sx-btn sx-btn--primary" type="button">Ок</button>
        </div>
      </div>`;
    document.addEventListener('DOMContentLoaded', ()=> document.body.appendChild(modal));
    modalTitle = modal.querySelector('.sx-modal__title');
    modalMsg   = modal.querySelector('.sx-modal__body');
    const close = ()=> modal.classList.remove('open');
    modal.querySelector('.sx-modal__x')?.addEventListener('click', close);
    modal.querySelector('.sx-modal__backdrop')?.addEventListener('click', close);
    modal.querySelector('.sx-btn--primary')?.addEventListener('click', close);
  }
  function showModal(title, html){
    ensureModal();
    modalTitle.textContent = title || 'Қате';
    modalMsg.innerHTML = html || '';
    modal.classList.add('open');
  }

  // -------- Busy helper --------
  function setBusy(el, busy=true){
    if (!el) return;
    el.toggleAttribute('data-busy', !!busy);
    const btn = el.matches('button, .sx-btn') ? el : el.querySelector('button[type="submit"], .sx-btn');
    if (btn){ btn.disabled = !!busy; btn.classList.toggle('is-busy', !!busy); }
  }

  // -------- API --------
  async function api(path, method='GET', data=null){
    const url = API_BASE + path.replace(/^\/+/, '');
    const ctrl = new AbortController();
    const t = setTimeout(()=> ctrl.abort(), TIMEOUT);
    const opts = { method, headers: { 'Accept':'application/json' }, signal: ctrl.signal, credentials: 'include' };
    if (data){ opts.headers['Content-Type'] = 'application/json; charset=utf-8'; opts.body = JSON.stringify(data); }
    try {
      const res = await fetch(url, opts);
      clearTimeout(t);
      const json = await res.json().catch(()=> ({}));
      if (!res.ok || json.error) throw new Error(json.error || `HTTP ${res.status}`);
      return json;
    } catch(e){ clearTimeout(t); throw e; }
  }

  // -------- Profile cache --------
  function cacheProfile(p){ try { sessionStorage.setItem(STORE_KEY, JSON.stringify(p||{})); } catch{} }
  function loadCachedProfile(){ try { return JSON.parse(sessionStorage.getItem(STORE_KEY)||'null'); } catch { return null; } }
  function clearCache(){ try { sessionStorage.removeItem(STORE_KEY); } catch{} }

  

  // -------- Sections --------
  function showSection(name){
    const m = { login:'#login-section', register:'#register-section', profile:'#profile-section' };
    Object.values(m).forEach(sel=>{ const el = $(sel); if (!el) return; el.classList.add('hidden'); el.setAttribute('hidden',''); });
    const target = m[name];
    if (target){ const el = $(target); if (el){ el.classList.remove('hidden'); el.removeAttribute('hidden'); } }
  }
  window.showSection = showSection; // support inline onclick

  // -------- Render & update --------
  function renderProfile(p){
    const logged = !!(p && p.id);
    if (logged){
      $('#profile-name')  && ($('#profile-name').value = p.name || '');
      $('#profile-email') && ($('#profile-email').value = p.email || '');
      $('#profile-role')  && ($('#profile-role').value = p.role || '');
      $('#profile-location') && ($('#profile-location').value = p.location || '');
      $('#profile-lang')  && ($('#profile-lang').value = p.lang || 'kk');
      const img = $('#profile-avatar');
      if (img) img.src = p.avatar || img.getAttribute('data-default') || '';
      const mail = $('#mailto-link'); if (mail && p.email){ mail.href = `mailto:${p.email}`; }
      showSection('profile');
    } else {
      showSection('login');
    }
  }

  async function refreshProfile(silent=true){
    try { const p = await api('profile.php','GET'); cacheProfile(p); renderProfile(p); return p; }
    catch(e){ clearCache(); if (!silent) showToast(e.message||'Қате','error'); renderProfile(null); return null; }
  }

  // -------- OAuth placeholders --------
  window.oauthLogin = function(provider){
    showModal('OAuth', `<p>${provider} арқылы кіру әзірленуде.</p>`);
  };

  // -------- Logout for inline onclick --------
  window.logout = async function(){
    const btn = $('.logout-btn');
    setBusy(btn, true);
    try { await api('logout.php','POST',{}); clearCache(); renderProfile(null); showToast('Шығу орындалды','ok'); }
    catch(e){ showToast(e.message||'Шығу қатесі','error'); }
    finally { setBusy(btn,false); }
  };

  // -------- Wire forms --------
  document.addEventListener('DOMContentLoaded', ()=>{

    // Login form
    const loginForm = $('#login-form');
    if (loginForm){
      loginForm.setAttribute('autocomplete','on');
      loginForm.addEventListener('submit', async (e)=>{
        e.preventDefault();
        setBusy(loginForm, true);
        try {
          const email = $('#login-email')?.value.trim();
          const password = $('#login-password')?.value || '';
          if (!email || !password) throw new Error('Email және құпиясөзді енгізіңіз.');
          await api('login.php','POST',{ email, password });
          showToast('Кіру сәтті!','ok');
          await refreshProfile(false);
        } catch(err){
          showToast(err.message||'Кіру қатесі','error',2600);
          showModal('Кіру қатесі', `<p>${err.message||'Белгісіз қате'}</p>`);
        } finally {
          setBusy(loginForm, false);
        }
      });
    }

    // Register form
    const regForm = $('#register-form');
    if (regForm){
      regForm.setAttribute('autocomplete','on');
      regForm.addEventListener('submit', async (e)=>{
        e.preventDefault();
        setBusy(regForm, true);
        try {
          const name = $('#reg-name')?.value.trim();
          const email = $('#reg-email')?.value.trim();
          const password = $('#reg-password')?.value || '';
          if (!name || !email || !password) throw new Error('Барлық өрістерді толтырыңыз.');
          if (password.length < 6) throw new Error('Құпиясөз 6 таңбадан кем болмау керек.');
          await api('register.php','POST',{ name, email, password });
          showToast('Тіркелу сәтті!','ok');
          $('#login-email') && ($('#login-email').value = email);
          showSection('login');
        } catch(err){
          showToast(err.message||'Тіркелу қатесі','error',2800);
          showModal('Тіркелу қатесі', `<p>${err.message||'Белгісіз қате'}</p>`);
        } finally {
          setBusy(regForm, false);
        }
      });
    }

    // Profile form
    const profileForm = $('#profile-form');
    if (profileForm){
      profileForm.setAttribute('autocomplete','on');
      profileForm.addEventListener('submit', async (e)=>{
        e.preventDefault();
        setBusy(profileForm, true);
        try {
          const data = {
            name: $('#profile-name')?.value.trim(),
            email: $('#profile-email')?.value.trim(),
            role: $('#profile-role')?.value.trim(),
            location: $('#profile-location')?.value.trim(),
            lang: $('#profile-lang')?.value.trim(),
          };
          const res = await api('update_profile.php','POST', data);
          cacheProfile(res.profile);
          renderProfile(res.profile);
          showToast('Профиль сақталды','ok');
        } catch(err){
          showToast(err.message||'Сақтау қатесі','error',2800);
          showModal('Профильді сақтау қатесі', `<p>${err.message||'Белгісіз қате'}</p>`);
        } finally {
          setBusy(profileForm, false);
        }
      });
    }

    // Avatar upload
    const avatarInput = $('#avatar-upload');
    if (avatarInput){
      avatarInput.addEventListener('change', async ()=>{
        const f = avatarInput.files && avatarInput.files[0]; if (!f) return;
        if (f.size > 2*1024*1024){ showToast('Файл тым үлкен (≤2MB).','error'); return; }
        const formData = new FormData(); formData.append('avatar', f);
        setBusy(avatarInput, true);
        try {
          const res = await fetch(API_BASE+'upload_avatar.php', { method:'POST', body:formData, credentials:'include' });
          const json = await res.json().catch(()=> ({}));
          if (!res.ok || json.error) throw new Error(json.error || `HTTP ${res.status}`);
          const img = $('#profile-avatar'); if (img) img.src = json.url;
          showToast('Аватар жүктелді','ok');
          try {
              const bc = new BroadcastChannel('salem_profile');
              bc.postMessage({
                type: 'avatar-changed',
                url: json.url,                 // новый URL аватара от бэка
                name: (window.currentUser && window.currentUser.name) || '',
                email: (window.currentUser && window.currentUser.email) || ''
              });
            } catch(_) {}

            try {
                const bc = new BroadcastChannel('salem_profile');
                bc.postMessage({
                  type: 'profile-updated',
                  profile: {
                    name:  data.name,
                    email: data.email,
                    avatar: document.getElementById('profile-avatar')?.src || '/static/avatar/default.png'
                  }
                });
              } catch(_) {}


          await refreshProfile(false);
        } catch(err){
          showToast(err.message||'Жүктеу қатесі','error',2800);
          showModal('Аватарды жүктеу қатесі', `<p>${err.message||'Белгісіз қате'}</p>`);
        } finally {
          setBusy(avatarInput, false);
          avatarInput.value = '';
        }
      });
    }

    // Initial render
    const cached = loadCachedProfile();
    if (cached && cached.id){ renderProfile(cached); refreshProfile(true); }
    else { renderProfile(null); refreshProfile(true); }
  });
})();