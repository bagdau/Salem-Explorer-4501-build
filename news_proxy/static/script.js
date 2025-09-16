// Salem News client (Edge-style) — полный файл
// Категории (можешь менять как угодно)
const categoryFeeds = {
  // Общие/международные
  main:        "https://news.google.com/rss?hl=ru&gl=KZ&ceid=KZ:ru",
  bbc:         "https://feeds.bbci.co.uk/news/rss.xml",
  bbc_world:   "https://feeds.bbci.co.uk/news/world/rss.xml",
  reuters:     "https://feeds.reuters.com/reuters/worldNews",
  guardian:    "https://www.theguardian.com/world/rss",
  cnn:         "https://rss.cnn.com/rss/edition.rss",
  aljazeera:   "https://www.aljazeera.com/xml/rss/all.xml",
  nytimes:     "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",

  // Технологии/диджитал
  techcrunch:  "https://techcrunch.com/feed/",
  verge:       "https://www.theverge.com/rss/index.xml",
  arstechnica: "https://feeds.arstechnica.com/arstechnica/index",
  hackernews:  "https://news.ycombinator.com/rss",

  // Казахстан через Google News (стабильно работает и с миниатюрами)
  tengrinews:  "https://news.google.com/rss/search?q=site:tengrinews.kz&hl=ru&gl=KZ&ceid=KZ:ru",
  zakon:       "https://news.google.com/rss/search?q=site:zakon.kz&hl=ru&gl=KZ&ceid=KZ:ru",
  informburo:  "https://news.google.com/rss/search?q=site:informburo.kz&hl=ru&gl=KZ&ceid=KZ:ru",
  nurkz:       "https://news.google.com/rss/search?q=site:nur.kz&hl=ru&gl=KZ&ceid=KZ:ru"
};


// ВАЖНО: фронт и API на одном origin → это порт :5000
const API_BASE = location.origin;

// DOM
const root          = document.getElementById('news-root');
const newsContainer = document.getElementById('newsContainer');
const catSelect     = document.getElementById('news-category');
const limitSelect   = document.getElementById('news-limit');
const statusEl      = document.getElementById('news-status');
const sourcesTA     = document.querySelector('[data-role="sources"]');
const refreshBtn    = document.getElementById('news-refresh');

// UI helpers
function setStatus(msg){ if(statusEl) statusEl.textContent = msg || ''; }
function textToSources(txt){ return (txt||'').split(/\n+/).map(s=>s.trim()).filter(Boolean); }
function uniqBy(arr, keyFn){ const seen=new Set(); return (arr||[]).filter(x=>{ const k=keyFn(x); if(seen.has(k)) return false; seen.add(k); return true; }); }
function stripHtml(s){ return (s||'').replace(/<[^>]+>/g,''); }
const clamp=(n,a,b)=>Math.max(a,Math.min(b,n));

// Человеческое «N минут назад» из формата "DD.MM.YYYY, HH:MM" или ISO
function timeAgo(dateStr){
  if(!dateStr) return '';
  let d;
  const m = String(dateStr).match(/^(\d{2})\.(\d{2})\.(\d{4}),\s*(\d{2}):(\d{2})$/);
  if(m) d = new Date(+m[3], +m[2]-1, +m[1], +m[4], +m[5], 0);
  else {
    const t = Date.parse(dateStr);
    d = isNaN(t) ? new Date() : new Date(t);
  }
  const diff = Math.max(0, Date.now() - d.getTime());
  const min = Math.floor(diff/60000);
  if(min < 1)  return 'только что';
  if(min < 60) return `${min} мин назад`;
  const h = Math.floor(min/60);
  if(h < 24)   return `${h} ч назад`;
  const ddd = Math.floor(h/24);
  return `${ddd} дн назад`;
}

// Картинки
function placeholderImg(){ return `${API_BASE}/img/news-placeholder.png`; }
function isLocalAsset(u){
  return typeof u === 'string' && (/^\/img\//.test(u) || u.startsWith(`${API_BASE}/img/`));
}
const prox = (u, ref) => `/api/proxy?url=${encodeURIComponent(u)}&ref=${encodeURIComponent(ref||'')}&fmt=webp&w=512&h=288&fit=cover&q=82`;

<img src={prox(googleImgUrl, 'https://news.google.com/')}
     referrerpolicy="no-referrer"
     loading="lazy"
     onerror="this.src='/img/news-placeholder.png'"/>


function imgFromDescription(html){
  if(!html) return '';
  const m = String(html).match(/<img[^>]+src=['"]([^'">]+)['"]/i);
  return (m && m[1]) ? m[1] : '';
}

// Нормализация ответа API к единому виду
function normalizeItem(n){
  const rawImage = n.image || imgFromDescription(n.description) || '';
  const title = n.title || 'Без названия';
  const link  = n.link  || '#';
  const descr = stripHtml(n.description || '').trim();
  const date  = n.pubDate || n.date || '';
  return {
    title,
    link,
    description: descr,
    pubDate: date,
    ago: date ? timeAgo(date) : '',
    // ВАЖНО: не подставляем плейсхолдер тут — пусть он будет только в рендере
    image: rawImage || '',
    source: n.source || n.creator || n.author || ''
  };
}


// Тянем фиды с тремя fallback’ами: /api/news → /api/news.php → POST /parse_feed
async function fetchNews({urls, limit, sort='latest', shuffle=false}){
  // 1) Современный
  try{
    const qs = new URLSearchParams();
    qs.set('limit', String(limit||10));
    qs.set('sort', sort);
    if (shuffle) qs.set('shuffle','1');
    if (urls?.length) qs.set('feeds', urls.join(','));
    const r = await fetch(`${API_BASE}/api/news?`+qs.toString(), { method:'GET' });
    if (r.ok){
      const data = await r.json();
      const items = Array.isArray(data) ? data : (data.items || []);
      if (items.length) return items.map(normalizeItem);
    }
  }catch(_) {}

  // 2) Легаси
  try{
    const qs = new URLSearchParams();
    qs.set('limit', String(limit||10));
    qs.set('sort', sort);
    if (shuffle) qs.set('shuffle','1');
    (urls||[]).forEach(u => qs.append('feed', u));
    const r = await fetch(`${API_BASE}/api/news.php?`+qs.toString(), { method:'GET' });
    if (r.ok){
      const items = await r.json();
      if (Array.isArray(items) && items.length) return items.map(normalizeItem);
    }
  }catch(_) {}

  // 3) Резерв (старый бэк): POST /parse_feed
  try{
    const alt = localStorage.getItem('news.alt') || API_BASE;
    const r = await fetch(`${alt}/parse_feed`, {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ urls, limit, shuffle:true })
    });
    if (r.ok){
      const data = await r.json();
      const arr  = Array.isArray(data) ? data : (data.items || []);
      if (arr.length) return arr.map(normalizeItem);
    }
  }catch(_) {}

  return [];
}

// Скелетоны на время загрузки
function showSkeletons(count=6){
  newsContainer.innerHTML = '';
  for(let i=0;i<count;i++){
    const sk = document.createElement('div');
    sk.className = 'news-edge-card';
    sk.innerHTML = `
      <div class="img-wrap"><div class="sk-img shimmer"></div></div>
      <div class="news-edge-content">
        <div class="sk-line shimmer"></div>
        <div class="sk-line shimmer short"></div>
        <div class="sk-line shimmer tiny"></div>
      </div>`;
    newsContainer.appendChild(sk);
  }
}

// Рендер карточек
function cardHTML(n, hero = false) {
  const cls = hero ? 'news-hero-card' : 'news-edge-card';
  const tag = n.source ? `<span class="chip">${n.source}</span>` : '';

  // если пусто → плейсхолдер
  // если локальный ассет → оставляем как есть
  // иначе проксируем
  let imgSrc;
  if (!n.image) {
    imgSrc = placeholderImg();
  } else if (isLocalAsset(n.image)) {
    imgSrc = n.image;
  } else {
    imgSrc = prox(n.image, n.link);
  }

  return `
  <article class="${cls}">
    <a class="img-wrap" href="${n.link}" target="_blank" rel="noopener">
      <img class="news-edge-img"
           loading="lazy"
           referrerpolicy="no-referrer"
           src="${imgSrc}"
           alt=""
           onerror="this.onerror=null;this.src='${placeholderImg()}'">
    </a>
    <div class="news-edge-content">
      <a href="${n.link}" target="_blank" rel="noopener" class="news-edge-title">${n.title}</a>
      ${n.description ? `<div class="news-edge-desc">${n.description}</div>` : ``}
      <div class="news-edge-meta">
        ${tag}
        ${n.ago ? `<span class="dot">•</span><time>${n.ago}</time>` : ``}
      </div>
    </div>
  </article>`;
}


function renderNewsEdge(list){
  newsContainer.innerHTML = '';
  if(!Array.isArray(list) || !list.length){
    newsContainer.innerHTML = '<div class="news-empty">Нет новостей.</div>';
    return;
  }
  // немного «героя» сверху и список далее
  const items = uniqBy(list, x => x.link);
  const hero  = items.slice(0,1);
  const rest  = items.slice(1);

  const html = [
    ...hero.map(n => cardHTML(n, true)),
    ...rest.map(n => cardHTML(n, false))
  ].join('');

  newsContainer.innerHTML = html;
}

// Главная загрузка
async function loadNews(){
  const cat    = catSelect?.value || 'main';
  const limit  = clamp(Number(limitSelect?.value || 12), 1, 100);
  const sources = textToSources(sourcesTA?.value || '');
  const urls   = sources.length ? sources : [ categoryFeeds[cat] || categoryFeeds.main ];

  setStatus('Жүктелуде…');
  showSkeletons(Math.min(limit, 12));

  try{
    const items = await fetchNews({urls, limit, sort:'latest'});
    renderNewsEdge(items);
    setStatus('');
  }catch(e){
    console.warn(e);
    newsContainer.innerHTML = '<div class="news-empty" style="color:#e11d48">Қате немесе CORS бөгеті. Тексер сервер API.</div>';
    setStatus('Ошибка');
  }
}

(function(){
  const root = document.getElementById('newsSlider');
  const track = document.getElementById('sliderTrack');
  const dotsBox = document.getElementById('sliderDots');
  const prevBtn = root.querySelector('.slider-btn.prev');
  const nextBtn = root.querySelector('.slider-btn.next');

  let idx = 0, total = 0;

  function slideTo(i){
    if (!total) return;
    idx = (i + total) % total;
    track.style.transform = `translateX(-${idx * 100}%)`;
    [...dotsBox.children].forEach((d, k) => d.classList.toggle('active', k === idx));
  }

  function buildFromNews(){
    const list = document.querySelectorAll('#newsContainer .news-edge-card');
    if (!list.length) return false;

    // соберём первые 6 карточек в слайды
    const slides = [];
    for (const card of Array.from(list).slice(0, 6)) {
      const link = card.querySelector('.news-edge-title')?.href || '#';
      const title = card.querySelector('.news-edge-title')?.textContent?.trim() || 'Без названия';
      const img = card.querySelector('.news-edge-img')?.src || '/img/news-placeholder.png';

      slides.push(`
        <div class="slide">
          <a href="${link}" target="_blank" rel="noopener">
            <img src="${img}" alt="">
            <div class="slide-caption">${title}</div>
          </a>
        </div>
      `);
    }

    if (!slides.length) return false;

    track.innerHTML = slides.join('');
    dotsBox.innerHTML = slides.map((_,i)=>`<div class="dot${i===0?' active':''}" data-i="${i}"></div>`).join('');
    total = slides.length;
    idx = 0;
    slideTo(0);
    return true;
  }

  // навигация
  prevBtn.addEventListener('click', () => slideTo(idx - 1));
  nextBtn.addEventListener('click', () => slideTo(idx + 1));
  dotsBox.addEventListener('click', (e) => {
    const d = e.target.closest('.dot'); if (!d) return;
    slideTo(parseInt(d.dataset.i,10) || 0);
  });

  // автоинициализация: попробуем сейчас…
  if (!buildFromNews()) {
    // …и подпишемся на изменения ленты (когда твой script.js дорисует новости)
    const obs = new MutationObserver(() => {
      if (buildFromNews()) obs.disconnect();
    });
    const listRoot = document.getElementById('newsContainer');
    if (listRoot) obs.observe(listRoot, { childList: true });
  }
})();

// события
refreshBtn?.addEventListener('click', loadNews);
catSelect?.addEventListener('change', loadNews);
limitSelect?.addEventListener('change', loadNews);
window.addEventListener('DOMContentLoaded', loadNews);
