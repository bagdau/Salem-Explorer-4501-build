const q = (s) => document.querySelector(s);

async function send(cmd, payload = {}) {
  return await chrome.runtime.sendMessage({ cmd, ...payload });
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function hostnameOf(url) {
  try { return new URL(url).hostname; } catch { return ""; }
}

async function refreshUI() {
  const tab = await activeTab();
  const host = hostnameOf(tab?.url || "");
  q("#site-host").textContent = host || "—";

  const state = await send("getState", { tabId: tab?.id ?? -1, host });
  q("#toggle-global").checked = !!state.enabled;
  q("#toggle-site").checked = !!state.siteBlocked;
  q("#stat-tab").textContent = state.tabBlocked ?? 0;
  q("#stat-total").textContent = state.totalBlocked ?? 0;

  // если глобально выключено — дизейблим свитч сайта
  q("#toggle-site").disabled = !state.enabled;
}

q("#toggle-global").addEventListener("change", async (e) => {
  const enabled = e.target.checked;
  await send("toggleEnabled", { enabled });
  await refreshUI();
});

q("#toggle-site").addEventListener("change", async (e) => {
  const tab = await activeTab();
  const host = hostnameOf(tab?.url || "");
  const block = e.target.checked;
  await send("toggleSite", { host, block });
  await refreshUI();
});

q("#btn-reset").addEventListener("click", async () => {
  await send("resetCounts");
  await refreshUI();
});

q("#btn-reload").addEventListener("click", async () => {
  const tab = await activeTab();
  if (tab?.id) chrome.tabs.reload(tab.id);
});

document.addEventListener("DOMContentLoaded", refreshUI);
