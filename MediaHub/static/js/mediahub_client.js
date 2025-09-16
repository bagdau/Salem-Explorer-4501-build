// static/js/mediahub_client.js
const API = location.origin.replace(/\/+$/, '');
const grid = document.getElementById('grid');
const kindSel = document.getElementById('kind');
const qInput = document.getElementById('q');
const btnRefresh = document.getElementById('btnRefresh');
const fileInput = document.getElementById('fileInput');
const folderInput = document.getElementById('folderInput');
const viewer = document.getElementById('viewer');
const statusEl = document.getElementById('status');

btnRefresh.onclick = loadList;
kindSel.onchange = loadList;
qInput.oninput = debounce(loadList, 300);

fileInput.onchange = async () => {
  if(!fileInput.files.length) return;
  await uploadFiles(fileInput.files); fileInput.value = ""; loadList();
};
folderInput.onchange = async () => {
  if(!folderInput.files.length) return;
  await uploadFiles(folderInput.files); folderInput.value = ""; loadList();
};

document.getElementById('btnImportDir').onclick = async () => {
  const path = prompt("Путь к папке на диске (индексировать без загрузки):");
  if(!path) return;
  const r = await fetch(API + '/api/import-dir', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path})
  });
  const j = await r.json();
  if(j.ok){ status(`Индексировано: ${j.indexed}`); loadList(); }
  else { status(j.error || 'Ошибка импорта'); }
};

async function uploadFiles(files){
  status('Загрузка...');
  const form = new FormData();
  for(const f of files) form.append('files', f, f.name);
  const r = await fetch(API + '/api/upload', { method:'POST', body: form });
  if(!r.ok){ status('Ошибка загрузки'); return; }
  const j = await r.json();
  status('Добавлено: ' + (j.files?.length || 0));
}

async function loadList(){
  status('Загрузка списка...');
  const params = new URLSearchParams();
  if(kindSel.value) params.set('kind', kindSel.value);
  if(qInput.value.trim()) params.set('q', qInput.value.trim());
  const r = await fetch(API + '/api/files?' + params.toString());
  if(!r.ok){ status('Не удалось загрузить список'); return; }
  const j = await r.json();
  renderGrid(j.items || []);
  status('Найдено: ' + (j.items?.length || 0));
}

function renderGrid(items){
  grid.innerHTML = '';
  for(const it of items){
    const card = document.createElement('div');
    card.className = 'card';
    const thumb = document.createElement('div');
    thumb.className = 'thumb';
    if(it.kind === 'image'){
      const img = document.createElement('img');
      img.src = it.src_url; img.alt = it.name;
      thumb.appendChild(img);
    }else if(it.kind === 'video'){
      thumb.textContent = '🎬 ' + (it.mime || '');
    }else if(it.kind === 'audio'){
      thumb.textContent = '🎵 ' + (it.mime || '');
    }else{
      thumb.textContent = '📄 ' + (it.mime || '');
    }
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.innerHTML = `<div class="name" title="${it.name}">${it.name}</div>
                      <div class="sub">${(it.size/1048576).toFixed(2)} MB · ${it.kind}</div>`;
    card.appendChild(thumb); card.appendChild(meta);
    card.onclick = () => openItem(it);
    grid.appendChild(card);
  }
}

function openItem(it){
  if(it.kind === 'video'){
    viewer.innerHTML = `<video src="${it.src_url}" controls preload="metadata"></video>`;
  }else if(it.kind === 'audio'){
    viewer.innerHTML = `<audio src="${it.src_url}" controls preload="metadata"></audio>`;
  }else if(it.kind === 'image'){
    viewer.innerHTML = `<img src="${it.src_url}" alt="${it.name}" style="max-width:100%;border-radius:10px">`;
  }else if(it.kind === 'doc'){
    const ext = it.name.split('.').pop().toLowerCase();
    if(ext === 'pdf'){
      viewer.innerHTML = `<iframe src="${it.src_url}" style="width:100%;height:70vh;border:none;border-radius:10px;background:#111"></iframe>`;
    }else{
      viewer.innerHTML = `<div class="hint">Формат не поддерживается для предпросмотра.</div>`;
    }
  }else{
    viewer.innerHTML = `<div class="hint">Неизвестный тип.</div>`;
  }
}

function status(t){ statusEl.textContent = t || ''; }
function debounce(fn, ms){ let t; return (...a)=>{ clearTimeout(t); t = setTimeout(()=>fn(...a), ms); }; }
loadList();