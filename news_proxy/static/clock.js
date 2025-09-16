// clock.js — Salem Clock (center-by-default, drag by header only, fixed close button)

(() => {
  const $  = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));

  // --- DOM
  const fab      = $('#clockFab');
  const modal    = $('#clockModal');
  const closeBtn = $('#clockClose');
  const card     = $('#slmCard');                  // карточка модалки
  const header   = $('#dragHandle') || card?.querySelector('.slmclk-head'); // тянем только за шапку

  const dial   = $('#salemClock');
  const face   = dial?.querySelector('.slmclk-face');
  const hourH  = dial?.querySelector('.slmclk-hand.hour');
  const minH   = dial?.querySelector('.slmclk-hand.minute');
  const secH   = dial?.querySelector('.slmclk-hand.second');
  const timeEl = $('#slmTime');
  const dateEl = $('#slmDate');

  // --- State / Keys
  const POS_KEY   = 'slmClockPos';
  const SEEN_KEY  = 'slmClockOpenedSession';
  const INITIAL_OFFSET_Y = 40;     // «чуть ниже» центра
  const DRAG_THRESHOLD   = 3;      // пикселей до начала реального драга

  let rafId = null;

  // ===================== CLOCK FACE =====================
  function buildTicks(){
    if(!face || !dial) return;
    $$('.slmclk-tick', face).forEach(n => n.remove());

    const R = dial.getBoundingClientRect().width/2 - 16;
    for(let i=0;i<60;i++){
      const t = document.createElement('div');
      t.className = 'slmclk-tick' + (i%5===0 ? ' hour' : '');
      const bar = document.createElement('i');
      t.appendChild(bar);

      const angle = i * 6;
      const len = (i%5===0 ? 18 : 10);

      t.style.transform =
        `translate(-50%,-50%) rotate(${angle}deg) translateY(${-R}px)`;
      bar.style.height = `${len}px`;
      bar.style.transform = `translateY(${-len/2}px)`;

      face.appendChild(t);
    }
  }

  function runClock(){
    const now = new Date();
    const ms  = now.getMilliseconds();
    const s   = now.getSeconds() + ms/1000;
    const m   = now.getMinutes() + s/60;
    const h   = (now.getHours()%12) + m/60;

    if(secH)  secH.style.transform  = `translate(-50%, -100%) rotate(${s*6}deg)`;
    if(minH)  minH.style.transform  = `translate(-50%, -100%) rotate(${m*6}deg)`;
    if(hourH) hourH.style.transform = `translate(-50%, -100%) rotate(${h*30}deg)`;

    if(timeEl) timeEl.textContent = now.toLocaleTimeString('ru-RU', {hour12:false});
    if(dateEl) dateEl.textContent = now.toLocaleDateString('ru-RU', {
      weekday:'long', day:'2-digit', month:'long', year:'numeric'
    });

    rafId = requestAnimationFrame(runClock);
  }

  // ===================== POSITIONING =====================
  const clamp = (v, min, max) => Math.min(Math.max(v, min), max);

  function clampToContainer(left, top){
    const pad = 8;
    const contW = modal.clientWidth;
    const contH = modal.clientHeight;
    const w = card.offsetWidth;
    const h = card.offsetHeight;

    const L = clamp(left, pad, contW - w - pad);
    const T = clamp(top,  pad, contH - h - pad);
    return {L, T};
  }

  // Центр с вертикальным сдвигом
  function centerCard(offsetY = INITIAL_OFFSET_Y){
    card.style.left = '50%';
    card.style.top  = '50%';
    card.style.transform = `translate(-50%, -50%) translateY(${offsetY}px)`;
  }

  function restorePosition(){
    try{
      const raw = localStorage.getItem(POS_KEY);
      if(!raw) return false;

      const pos = JSON.parse(raw);
      card.style.transform = 'none';
      const p = clampToContainer(Number(pos.left)||0, Number(pos.top)||0);
      card.style.left = `${p.L}px`;
      card.style.top  = `${p.T}px`;
      return true;
    }catch{ return false; }
  }

  function savePosition(){
    localStorage.setItem(POS_KEY, JSON.stringify({
      left: parseFloat(card.style.left) || 0,
      top:  parseFloat(card.style.top)  || 0
    }));
  }

  // ===================== MODAL OPEN/CLOSE =====================
  function openModal(){
    modal.setAttribute('aria-hidden','false');

    buildTicks();
    cancelAnimationFrame(rafId);
    runClock();

    // Первый показ в этой вкладке — всегда по центру (с оффсетом)
    if (!sessionStorage.getItem(SEEN_KEY)) {
      centerCard();
      sessionStorage.setItem(SEEN_KEY, '1');
    } else {
      restorePosition() || centerCard();
    }
  }

  function closeModal(){
    modal.setAttribute('aria-hidden','true');
    cancelAnimationFrame(rafId);
  }

  function toggleModal(){
    (modal.getAttribute('aria-hidden') === 'true') ? openModal() : closeModal();
  }

  // ===================== DRAG BY HEADER ONLY =====================
  let isDown = false, dragging = false, captured = false;
  let pointerId = null, startX = 0, startY = 0, startLeft = 0, startTop = 0;

  const isInteractive = el =>
    !!el.closest('#clockClose, button, a, input, textarea, select, label, [data-no-drag]');

  function onPointerDown(e){
    if(e.button !== 0) return; // ЛКМ/эквивалент
    if(modal.getAttribute('aria-hidden') === 'true') return;
    if(isInteractive(e.target)) return;

    const contRect = modal.getBoundingClientRect();
    const rect = card.getBoundingClientRect();

    // Переводим translate в абсолютные px внутри модалки
    card.style.left = `${rect.left - contRect.left}px`;
    card.style.top  = `${rect.top  - contRect.top }px`;
    card.style.transform = 'none';

    startX = e.clientX; startY = e.clientY;
    startLeft = parseFloat(card.style.left);
    startTop  = parseFloat(card.style.top);

    isDown = true;
    dragging = false;
    pointerId = e.pointerId;

    document.body.classList.add('no-select');
    // Не preventDefault здесь — даём кликам жить до начала реального драга
  }

  function onPointerMove(e){
    if(!isDown || (pointerId !== null && e.pointerId !== pointerId)) return;

    const dx = e.clientX - startX;
    const dy = e.clientY - startY;

    // Порог до включения "настоящего" перетаскивания
    if(!dragging && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      dragging = true;
      header.classList.add('dragging');
      card.classList.add('dragging');
      try { header.setPointerCapture(pointerId); captured = true; } catch {}
    }

    if(!dragging) return;

    const {L, T} = clampToContainer(startLeft + dx, startTop + dy);
    card.style.left = `${L}px`;
    card.style.top  = `${T}px`;
  }

  function onPointerEnd(){
    if(!isDown) return;

    if(captured){
      try { header.releasePointerCapture(pointerId); } catch {}
    }
    isDown = false;
    captured = false;
    pointerId = null;

    if(dragging){
      savePosition();
    }

    dragging = false;
    header.classList.remove('dragging');
    card.classList.remove('dragging');
    document.body.classList.remove('no-select');
  }

  // ===================== EVENTS =====================
  if(fab)      fab.addEventListener('click', toggleModal);
  if(modal)    modal.addEventListener('click', (e) => { if(e.target === modal) closeModal(); });

  // Кнопка ×: стопим всплытие pointerdown, чтобы не запускать drag
  if(closeBtn){
    closeBtn.addEventListener('click', closeModal);
    closeBtn.addEventListener('pointerdown', (e) => e.stopPropagation());
  }

  window.addEventListener('keydown', (e) => {
    if(e.key === 'Escape' && modal.getAttribute('aria-hidden') === 'false') closeModal();
    if(e.altKey && e.key.toLowerCase() === 'c'){ e.preventDefault(); toggleModal(); }
  });

  window.addEventListener('resize', () => {
    if(modal.getAttribute('aria-hidden') === 'false'){
      buildTicks();
      // Оставить внутри видимой области
      restorePosition() || centerCard();
    }
  });

  if(header){
    header.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerEnd);
    window.addEventListener('pointercancel', onPointerEnd);
  }
})();
