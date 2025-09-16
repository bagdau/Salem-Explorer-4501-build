(function(){"use strict";
// Autoplay Iframe Plugin — parent + child in one file
const DOC = document;
const WIN = window;
const isTop = (()=>{ try { return WIN.top === WIN; } catch{ return true; } })();
const THIS_URL = (DOC.currentScript && DOC.currentScript.src) || "";

// Shared gate
function installAutoplayGate(rootWin){
  if (rootWin.__autoplayGateInstalled) return;
  rootWin.__autoplayGateInstalled = true;
  const pending = new Set();
  let userGesture = false;
  try{
    const origPlay = rootWin.HTMLMediaElement && rootWin.HTMLMediaElement.prototype.play;
    if (origPlay && !rootWin.HTMLMediaElement.prototype.__autoplayGatePatched){
      rootWin.HTMLMediaElement.prototype.__autoplayGatePatched = true;
      rootWin.HTMLMediaElement.prototype.play = function(){
        const media = this;
        try{
          const p = origPlay.apply(media, arguments);
          if (p && typeof p.catch === "function"){
            p.catch(err=>{
              if (!userGesture && err && (err.name === "NotAllowedError" || String(err).includes("NotAllowedError"))){
                pending.add(media);
                return; // swallow
              }
            });
          }
          return p;
        }catch(err){
          if (!userGesture && err && (err.name === "NotAllowedError" || String(err).includes("NotAllowedError"))){
            pending.add(media);
            return Promise.resolve();
          }
          throw err;
        }
      };
    }
  }catch{}
  function enableAll(){
    userGesture = true;
    try{ pending.forEach(m=>{ try{ m.play().catch(()=>{});}catch{}}); }catch{}
    pending.clear();
  }
  rootWin.addEventListener("pointerdown", enableAll, { once:true, capture:true });
  rootWin.addEventListener("unhandledrejection", (e)=>{
    const r = e && (e.reason || {});
    const txt = typeof r === "string" ? r : (r && (r.name || r.message) || "");
    if (String(txt).includes("NotAllowedError")) { e.preventDefault(); }
  });
  return { enableAll };
}

function sameOrigin(iframe){
  try{ const w = iframe.contentWindow; if (!w) return false; void w.location.href; return true; }catch{ return false; }
}

function setAllowAttr(iframe){
  const allow = iframe.getAttribute("allow") || "";
  const need = ["autoplay","fullscreen","encrypted-media","picture-in-picture"];
  const set = new Set(allow.split(";").map(s=>s.trim()).filter(Boolean));
  let changed = false;
  need.forEach(t=>{ if(!Array.from(set).some(s=>s.startsWith(t))){ set.add(t); changed = true; } });
  if (changed) iframe.setAttribute("allow", Array.from(set).join("; "));
}

function injectIntoSameOrigin(iframe){
  try{
    const d = iframe.contentDocument; if (!d) return;
    if (d.documentElement.querySelector('script[data-autoplay-plugin]')) return;
    const s = d.createElement('script'); s.src = THIS_URL; s.async = false; s.setAttribute('data-autoplay-plugin','');
    (d.head || d.documentElement).appendChild(s);
  }catch{}
}

function parentMain(){
  const gate = installAutoplayGate(WIN);
  const frames = new Set();
  function handle(iframe){ if (!iframe || frames.has(iframe)) return; frames.add(iframe); setAllowAttr(iframe); if (sameOrigin(iframe)) injectIntoSameOrigin(iframe); iframe.addEventListener('load', ()=>{ setAllowAttr(iframe); if (sameOrigin(iframe)) injectIntoSameOrigin(iframe); }, { once:true }); }
  DOC.querySelectorAll('iframe').forEach(handle);
  const mo = new MutationObserver((muts)=>{
    muts.forEach(m=>{
      m.addedNodes && m.addedNodes.forEach(node=>{ if (node && node.tagName === 'IFRAME') handle(node); });
      if (m.type==='attributes' && m.target && m.target.tagName==='IFRAME'){ setAllowAttr(m.target); }
    });
  });
  mo.observe(DOC.documentElement, { childList:true, subtree:true, attributes:true, attributeFilter:['src','allow'] });
  function broadcastEnable(){ try{ DOC.querySelectorAll('iframe').forEach(f=>{ try{ f.contentWindow && f.contentWindow.postMessage({ type:'salem_autoplay_enable' }, '*'); }catch{} }); }catch{} }
  WIN.addEventListener('pointerdown', ()=>{ gate && gate.enableAll && gate.enableAll(); broadcastEnable(); }, { once:true, capture:true });
}

function childMain(){
  const gate = installAutoplayGate(WIN);
  function playAuto(){
    try{
      const list = DOC.querySelectorAll('video[autoplay], audio[autoplay], video[data-autoplay], audio[data-autoplay]');
      list.forEach(el=>{
        const can = (el.muted === true) || el.hasAttribute('data-autoplay-force');
        if (can){ try{ el.play().catch(()=>{}); }catch{} }
      });
    }catch{}
  }
  WIN.addEventListener('message', (ev)=>{
    const d = ev && ev.data; if (!d || typeof d !== 'object') return;
    if (d.type === 'salem_autoplay_enable'){ gate && gate.enableAll && gate.enableAll(); playAuto(); }
  });
  // Если в iframe уже произошёл клик — попытаться сразу
  WIN.addEventListener('pointerdown', ()=>{ gate && gate.enableAll && gate.enableAll(); playAuto(); }, { once:true, capture:true });
}

if (isTop) parentMain(); else childMain();
})();
