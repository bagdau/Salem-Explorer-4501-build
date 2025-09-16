/*! News Block — Salem Explorer. UMD-style: window.NewsBlock.init(el, options) */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) { module.exports = factory(); }
  else { root.NewsBlock = factory(); }
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  const DEFAULTS = {
    sources: [
      "https://news.google.com/rss?hl=ru&gl=KZ&ceid=KZ:ru",
      "https://www.bing.com/news/search?q=Казахстан&format=RSS",
      "https://news.yandex.ru/index.rss"
    ],
    limit: 12,
    intervalMin: 10,
    rotateImages: true,
    useProxy: true,
    proxyUrl: "https://api.allorigins.win/raw?url=",
    storageKey: "salem.news.settings.v1"
  };

  function $(s, r){ return (r||document).querySelector(s); }
  function $$(s, r){ return Array.from((r||document).querySelectorAll(s)); }

  function sourceName(url){ try { return new URL(url).hostname.replace(/^www\./,''); } catch { return 'источник'; } }
  function fmtTime(s){ const d=new Date(s); return isNaN(d)?'':d.toLocaleString('ru-RU',{hour:'2-digit',minute:'2-digit'}); }

  async function fetchText(url, useProxy, proxyUrl, timeoutMs=12000){
    const controller = new AbortController(); const id = setTimeout(()=> controller.abort(), timeoutMs);
    try {
      const r = await fetch(url, { signal: controller.signal });
      if(!r.ok) throw new Error('HTTP '+r.status);
      return await r.text();
    } catch (err){
      if(!useProxy) throw err;
      const proxies = [
        proxyUrl,
        "https://r.jina.ai/http://",
        "https://api.rss2json.com/v1/api.json?rss_url="
      ];
      for (const p of proxies){
        try{
          const proxied = p.includes('http') ? (p + encodeURIComponent(url)) : (p + url.replace(/^https?:\/\//i,''));
          const r = await fetch(proxied);
          if(!r.ok) throw new Error('Proxy HTTP '+r.status);
          return await r.text();
        }catch(e2){/* next */}
      }
      throw err;
    } finally { clearTimeout(id); }
  }

  function parseRSS(xmlStr){
    const out=[]; if(!xmlStr) return out;
    const dom = new DOMParser().parseFromString(xmlStr, 'text/xml');
    if(dom.querySelector('parsererror')) return out;
    const items = dom.querySelectorAll('item, entry');
    items.forEach(it=>{
      const get = (q)=> it.querySelector(q)?.textContent?.trim() || '';
      let title = get('title');
      let link = it.querySelector('link')?.getAttribute('href') || get('link');
      let pub  = get('pubDate') || get('updated') || get('published');
      let desc = get('description') || get('summary') || get('content') || get('content\\:encoded');
      const imgs=[];
      it.querySelectorAll('media\\:content, media\\:thumbnail, enclosure').forEach(n=>{
        const url = n.getAttribute('url'); const type=n.getAttribute('type')||'';
        if(url && (!type || type.startsWith('image'))) imgs.push(url);
      });
      const tmp = document.createElement('div'); tmp.innerHTML = desc || '';
      tmp.querySelectorAll('img').forEach(im=>{ const s=im.getAttribute('src'); if(s) imgs.push(s); });
      title = (title||'').replace(/<[^>]+>/g,'').slice(0,200);
      const clean = tmp.textContent.trim().replace(/\s+/g,' ').slice(0,240);
      out.push({ title, link, desc:clean, pub, images:[...new Set(imgs)].slice(0,5) });
    });
    return out;
  }

  function parseJSONFeed(txt){
    try{
      const data = JSON.parse(txt);
      if (data && data.items && Array.isArray(data.items)) {
        if (data.status === 'ok' || data.feed) {
          return data.items.map(it=>({
            title: it.title || '',
            link: it.link || it.url || '',
            desc: (it.description || it.content || '').replace(/<[^>]+>/g,'').slice(0,240),
            pub: it.pubDate || it.published || it.updated || '',
            images: [it.thumbnail, it.enclosure?.link, it.enclosure?.url].filter(Boolean).slice(0,5)
          }));
        }
        return data.items.map(it=>({
          title: it.title || '',
          link: it.url || it.external_url || '',
          desc: (it.content_text || it.summary || '').slice(0,240),
          pub: it.date_published || it.date_modified || '',
          images: (it.attachments||[]).filter(a=>/^image\//.test(a.mime_type||'')).map(a=>a.url).slice(0,5)
        }));
      }
    }catch{}
    return [];
  }

  function cardTemplate(a, src){
    const img0 = a.images && a.images[0] ? a.images[0] : '';
    const when = fmtTime(a.pub);
    return (
      '<article class="sx-card" data-images=' + JSON.stringify(a.images||[]).replace(/'/g,'&apos;') + '>' +
        '<div class="sx-imgwrap">' +
          '<img class="sx-img ' + (img0?'show':'') + '" src="' + (img0||'') + '" alt="">' +
        '</div>' +
        '<div class="sx-body">' +
          '<a class="sx-h" href="' + (a.link||'#') + '" target="_blank" rel="noopener">' + (a.title || '(без названия)') + '</a>' +
          '<div class="sx-meta"><span>' + src + '</span>' + (when?('<span>• ' + when + '</span>'):'') + '</div>' +
          '<div class="sx-desc">' + (a.desc||'') + '</div>' +
        '</div>' +
      '</article>'
    );
  }

  function init(el, options){
    if(!el) throw new Error('NewsBlock.init: container element required');
    const state = {
      el,
      opts: Object.assign({}, DEFAULTS, (options||{})),
      timers: new Map(),
      refreshTimer: null
    };

    // Hook DOM within this block
    const grid = el.querySelector('[data-role="grid"]');
    const settings = el.querySelector('.sx-settings');
    const ui = {
      refresh: el.querySelector('[data-action="refresh"]'),
      settingsBtn: el.querySelector('[data-action="settings"]'),
      save: el.querySelector('[data-action="save"]'),
      cancel: el.querySelector('[data-action="cancel"]'),
      sources: el.querySelector('[data-role="sources"]'),
      limit: el.querySelector('[data-role="limit"]'),
      interval: el.querySelector('[data-role="interval"]'),
      rotate: el.querySelector('[data-role="rotate"]'),
      useProxy: el.querySelector('[data-role="useProxy"]'),
      proxy: el.querySelector('[data-role="proxy"]')
    };

    // Try to read persisted settings
    try{
      const saved = JSON.parse(localStorage.getItem(state.opts.storageKey) || '{}');
      Object.assign(state.opts, saved);
    }catch{}

    // Prefill UI
    ui.sources.value = (state.opts.sources||[]).join('\n');
    ui.limit.value = state.opts.limit;
    ui.interval.value = state.opts.intervalMin;
    ui.rotate.checked = !!state.opts.rotateImages;
    ui.useProxy.checked = !!state.opts.useProxy;
    ui.proxy.value = state.opts.proxyUrl || '';

    // UI events
    ui.settingsBtn.addEventListener('click', ()=> { settings.hidden = !settings.hidden; });
    ui.cancel.addEventListener('click', ()=> { settings.hidden = true; });
    ui.save.addEventListener('click', ()=> {
      state.opts.sources = ui.sources.value.split(/\n+/).map(s=>s.trim()).filter(Boolean);
      state.opts.limit = Math.max(3, Math.min(48, Number(ui.limit.value)||12));
      state.opts.intervalMin = Math.max(5, Math.min(120, Number(ui.interval.value)||10));
      state.opts.rotateImages = !!ui.rotate.checked;
      state.opts.useProxy = !!ui.useProxy.checked;
      state.opts.proxyUrl = (ui.proxy.value || DEFAULTS.proxyUrl).trim();
      localStorage.setItem(state.opts.storageKey, JSON.stringify({
        sources: state.opts.sources,
        limit: state.opts.limit,
        intervalMin: state.opts.intervalMin,
        rotateImages: state.opts.rotateImages,
        useProxy: state.opts.useProxy,
        proxyUrl: state.opts.proxyUrl
      }));
      settings.hidden = true;
      scheduleAuto(); loadNews();
    });
    ui.refresh.addEventListener('click', loadNews);

    function clearImageTimers(){
      state.timers.forEach(id => clearInterval(id));
      state.timers.clear();
    }

    function setupImageRotation(){
      clearImageTimers();
      if(!state.opts.rotateImages) return;
      const io = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          const card = entry.target;
          if(!entry.isIntersecting) return;
          if(state.timers.has(card)) return;
          const imgs = JSON.parse(card.getAttribute('data-images') || '[]');
          if(!imgs || imgs.length <= 1) return;
          let i = 0; const imgEl = card.querySelector('.sx-img');
          const t = setInterval(() => {
            i = (i + 1) % imgs.length;
            const next = imgs[i];
            if(!imgEl) return;
            imgEl.classList.remove('show');
            setTimeout(() => { imgEl.src = next; imgEl.onload = () => imgEl.classList.add('show'); }, 140);
          }, 3000);
          state.timers.set(card, t);
        });
      }, { threshold: .1 });
      $$('.sx-card', el).forEach(c => io.observe(c));
    }

    async function loadNews(){
      grid.innerHTML = '<div class="sx-news-empty">Загружаем…</div>';
      try{
        const all = [];
        for(const src of state.opts.sources){
          try{
            const raw = await fetchText(src, state.opts.useProxy, state.opts.proxyUrl);
            const first = raw.trim().charAt(0);
            const chunk = (first === '{' || first === '[') ? parseJSONFeed(raw) : parseRSS(raw);
            chunk.slice(0, Math.ceil(state.opts.limit*1.3/state.opts.sources.length)).forEach(it => {
              all.push(Object.assign({_src: sourceName(src)}, it));
            });
          }catch(e){ console.warn('Source failed:', src, e); }
        }
        all.sort((a,b)=> new Date(b.pub||0) - new Date(a.pub||0));
        const pick = all.slice(0, state.opts.limit);
        if(!pick.length){ grid.innerHTML = '<div class="sx-news-empty">Не удалось загрузить новости. Проверьте источники/прокси.</div>'; clearImageTimers(); return; }
        grid.innerHTML = pick.map(a => cardTemplate(a, a._src)).join('');
        setupImageRotation();
      }catch(e){
        grid.innerHTML = '<div class="sx-news-empty">Ошибка загрузки новостей.</div>';
        clearImageTimers();
      }
    }

    function scheduleAuto(){
      if(state.refreshTimer) clearInterval(state.refreshTimer);
      state.refreshTimer = setInterval(loadNews, Math.max(5, state.opts.intervalMin) * 60 * 1000);
    }

    scheduleAuto(); loadNews();

    // Public API on this instance (optional)
    return {
      reload: loadNews,
      update(opts){ Object.assign(state.opts, opts||{}); scheduleAuto(); loadNews(); },
      destroy(){
        if(state.refreshTimer) clearInterval(state.refreshTimer);
        clearImageTimers();
        grid.innerHTML = '<div class="sx-news-empty">Отключено.</div>';
      }
    };
  }

  return { init };
}));
