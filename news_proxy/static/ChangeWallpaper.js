// static/ChangeWallpaper.js
(() => {
  const LS_KEY = 'slm.bg'; // { type:'image'|'video', src:string, name?:string, isDataURL?:boolean, ts?:number }

  // Публичные API для index.html
  window.triggerBackgroundInput = function (type) {
    if (type === 'image') document.getElementById('bgImageInput')?.click();
    else if (type === 'video') document.getElementById('bgVideoInput')?.click();
  };
  window.resetBackground = function () {
    try { localStorage.removeItem(LS_KEY); } catch {}
    applyFromLS();
  };

  const readLS  = () => { try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null'); } catch { return null; } };
  const writeLS = (obj) => { try { localStorage.setItem(LS_KEY, JSON.stringify({ ...obj, ts: Date.now() })); } catch {} };

  // Гарантируем слои (ВИДИМЫЕ поверх body: z-index:0)
  function ensureLayers() {
    let bg = document.getElementById('dynamic-bg');
    if (!bg) {
      bg = document.createElement('div');
      bg.id = 'dynamic-bg';
      bg.style.cssText = [
        'position:fixed','inset:0','background-size:cover','background-position:center',
        'z-index:0','transition:opacity .35s','pointer-events:none'
      ].join(';');
      document.body.prepend(bg);
    }
    let vid = document.getElementById('dynamic-bg-video');
    if (!vid) {
      vid = document.createElement('video');
      vid.id = 'dynamic-bg-video';
      Object.assign(vid, { muted:true, loop:true, playsInline:true, autoplay:true });
      vid.style.cssText = [
        'position:fixed','inset:0','width:100%','height:100%','object-fit:cover',
        'z-index:0','opacity:0','transition:opacity .35s','pointer-events:none'
      ].join(';');
      document.body.prepend(vid);
    }
    return { bg, vid };
  }

  // Применение
  function applyFromLS() {
    const saved = readLS();
    const { bg, vid } = ensureLayers();

    if (!saved) {
      bg.style.backgroundImage = 'none';
      bg.style.opacity = '0';
      vid.pause(); vid.removeAttribute('src'); vid.load?.(); vid.style.opacity = '0';
      return;
    }
    if (saved.type === 'image') {
      vid.pause(); vid.removeAttribute('src'); vid.load?.(); vid.style.opacity = '0';
      bg.style.backgroundImage = `url("${saved.src}")`;
      bg.style.opacity = '1';
    } else { // video
      bg.style.backgroundImage = 'none';
      bg.style.opacity = '1';
      vid.src = saved.src; vid.currentTime = 0;
      vid.play().catch(() => {});
      vid.style.opacity = '1';
    }
  }

  // Обработчики выбора (СОХРАНЯЕМ в DataURL, а не blob:), чтобы работало после перезапуска
  const imgInput = document.getElementById('bgImageInput');
  if (imgInput) imgInput.onchange = e => {
    const f = e.target.files?.[0]; if (!f) return;
    const rdr = new FileReader();
    rdr.onload = ev => { writeLS({ type:'image', src:String(ev.target.result), name:f.name, isDataURL:true }); applyFromLS(); };
    rdr.readAsDataURL(f);
  };

  const vidInput = document.getElementById('bgVideoInput');
  if (vidInput) vidInput.onchange = e => {
    const f = e.target.files?.[0]; if (!f) return;
    const rdr = new FileReader();
    rdr.onload = ev => { writeLS({ type:'video', src:String(ev.target.result), name:f.name, isDataURL:true }); applyFromLS(); };
    rdr.readAsDataURL(f);
  };

  // Реакция на изменения из других вкладок
  window.addEventListener('storage', (ev) => { if (ev.key === LS_KEY) applyFromLS(); });

  // Применяем при загрузке
  window.addEventListener('DOMContentLoaded', applyFromLS);
})();
