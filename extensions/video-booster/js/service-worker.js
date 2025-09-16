// MV3 service worker. Управляет динамическими правилами DNR,
// вайтлистом и статой блокировок.

const STORAGE_KEY = "salem_cleanstream_state";
const DEFAULT_STATE = {
  enabled: true,
  allowlist: [],       // домены, где блокировка отключена
  counts: { total: 0 },// накопитель для onRuleMatchedDebug
};

const RULE_IDS = {
  // Следим за ID — они неизменны при пересборке правил
  start: 1000
};

// Базовые правила — специально короткий набор, чтобы не «ломать» сайты.
// Вы всегда можете расширить список.
const BASE_RULES = [
  // Google Ads / DoubleClick
  { urlFilter: "googleads.g.doubleclick.net", resourceTypes: ["xmlhttprequest","image","media","script","sub_frame"] },
  { urlFilter: "doubleclick.net", resourceTypes: ["xmlhttprequest","image","media","script","sub_frame"] },
  { urlFilter: "googlesyndication.com", resourceTypes: ["xmlhttprequest","image","media","script","sub_frame"] },
  { urlFilter: "googleadservices.com", resourceTypes: ["xmlhttprequest","image","media","script","sub_frame"] },
  // YouTube ad telemetry & ad endpoints
  { urlFilter: "youtube.com/api/stats/ads", resourceTypes: ["xmlhttprequest"] },
  { urlFilter: "youtube.com/get_midroll_", resourceTypes: ["xmlhttprequest"] },
  // Generic noisy ad CDNs
  { urlFilter: ".adnxs.com", resourceTypes: ["xmlhttprequest","image","script","sub_frame"] },
  { urlFilter: ".scorecardresearch.com", resourceTypes: ["xmlhttprequest","image","script"] },
  { urlFilter: ".rubiconproject.com", resourceTypes: ["xmlhttprequest","image","script"] },
  { urlFilter: ".criteo.com", resourceTypes: ["xmlhttprequest","image","script"] }
];

// ——————————————————————————— helpers ———————————————————————————

async function getState() {
  const stored = await chrome.storage.local.get(STORAGE_KEY);
  return { ...DEFAULT_STATE, ...(stored[STORAGE_KEY] || {}) };
}
async function setState(next) {
  await chrome.storage.local.set({ [STORAGE_KEY]: next });
  return next;
}

function nextRuleId(i) {
  return RULE_IDS.start + i;
}

function buildRules(allowlist) {
  // Превращаем BASE_RULES в DNR-правила с учётом вайтлиста
  // Вайтлист применяем через excludedInitiatorDomains (топ-фрейм домен)
  const excluded = dedupe((allowlist || []).map(normalizeHost));
  return BASE_RULES.map((r, i) => ({
    id: nextRuleId(i),
    priority: 1,
    action: { type: "block" },
    condition: {
      urlFilter: r.urlFilter,
      resourceTypes: r.resourceTypes,
      domainType: "thirdParty",
      excludedInitiatorDomains: excluded.length ? excluded : undefined
    }
  }));
}

function dedupe(a) { return [...new Set(a.filter(Boolean))]; }
function normalizeHost(h) {
  if (!h) return "";
  return h.replace(/^https?:\/\//, "").replace(/\/.*$/, "").toLowerCase();
}

// Пересобираем динамические правила согласно state
async function rebuildRules(state) {
  const rules = state.enabled ? buildRules(state.allowlist) : [];
  const remove = BASE_RULES.map((_, i) => nextRuleId(i));
  if (rules.length) {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: remove,
      addRules: rules
    });
  } else {
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: remove
    });
  }
}

// ——————————————————————————— events ———————————————————————————

chrome.runtime.onInstalled.addListener(async () => {
  const state = await setState(DEFAULT_STATE);
  await rebuildRules(state);
});

chrome.runtime.onStartup.addListener(async () => {
  const state = await getState();
  await rebuildRules(state);
});

// Статистика по срабатываниям (нужна declarativeNetRequestFeedback)
const COUNTS_BY_TAB = new Map(); // tabId -> count
chrome.declarativeNetRequest.onRuleMatchedDebug?.addListener((info) => {
  const tabId = info?.request?.tabId;
  if (typeof tabId === "number" && tabId >= 0) {
    COUNTS_BY_TAB.set(tabId, (COUNTS_BY_TAB.get(tabId) || 0) + 1);
  }
  // общий счётчик
  getState().then((s) => setState({ ...s, counts: { total: (s.counts?.total || 0) + 1 } }));
});

// Горячая клавиша — глобальный тумблер
chrome.commands?.onCommand.addListener(async (cmd) => {
  if (cmd !== "toggle-enabled") return;
  const s = await getState();
  s.enabled = !s.enabled;
  await setState(s);
  await rebuildRules(s);
});

// ——————————————————————————— messaging ———————————————————————————

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    const s = await getState();

    if (msg.cmd === "getState") {
      const tabId = msg.tabId ?? -1;
      const host = normalizeHost(msg.host);
      const siteBlocked = !s.allowlist.includes(host);
      sendResponse({
        enabled: s.enabled,
        siteBlocked,
        tabBlocked: COUNTS_BY_TAB.get(tabId) || 0,
        totalBlocked: s.counts?.total || 0
      });
      return;
    }

    if (msg.cmd === "toggleEnabled") {
      s.enabled = !!msg.enabled;
      await setState(s);
      await rebuildRules(s);
      sendResponse({ ok: true, enabled: s.enabled });
      return;
    }

    if (msg.cmd === "toggleSite") {
      const host = normalizeHost(msg.host);
      const block = !!msg.block; // true → НЕ в вайтлисте
      const set = new Set(s.allowlist || []);
      if (block) set.delete(host); else set.add(host);
      s.allowlist = [...set];
      await setState(s);
      await rebuildRules(s);
      sendResponse({ ok: true, allowlist: s.allowlist });
      return;
    }

    if (msg.cmd === "resetCounts") {
      s.counts = { total: 0 };
      await setState(s);
      COUNTS_BY_TAB.clear();
      sendResponse({ ok: true });
      return;
    }

    sendResponse({ ok: false, error: "unknown-cmd" });
  })();

  return true; // async
});
