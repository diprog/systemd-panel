"use strict";

/*
  UI/UX refresh:
  - Soft cards, warm accent color, subtle rings and shadows
  - Skeletons for initial and manual refresh loads
  - Toast notifications on actions and errors
  - Smoother logs drawer open/close transitions
*/

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

let statusSource = null;
let logSource = null;

// --------------------- Crypto utils ---------------------
async function sha256Hex(str) {
  const data = new TextEncoder().encode(str);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function hmacSha256Hex(keyHex, message) {
  const keyBytes = Uint8Array.from(keyHex.match(/.{2}/g).map((h) => parseInt(h, 16)));
  const cryptoKey = await crypto.subtle.importKey("raw", keyBytes, { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", cryptoKey, new TextEncoder().encode(message));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// --------------------- API helpers ----------------------
async function getJSON(url) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error(await safeText(res));
  return await res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await safeText(res));
  return await res.json();
}

async function safeText(res) {
  try {
    return await res.text();
  } catch {
    return "Request failed";
  }
}

// --------------------- Tiny UI primitives ----------------
function spinner(size = 16, cls = "") {
  return `<svg class="animate-spin" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-opacity=".15" stroke-width="4"/>
    <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" stroke-width="4" stroke-linecap="round"/>
  </svg>`;
}

function icon(name, size = 16) {
  const m = {
    play: `<path d="M8 5v14l11-7L8 5z"/>`,
    stop: `<path d="M6 6h12v12H6z"/>`,
    restart: `<path d="M12 6V3L8 7l4 4V8c2.76 0 5 2.24 5 5a5 5 0 0 1-8.66 3.54 1 1 0 1 0-1.41 1.41A7 7 0 0 0 19 13c0-3.86-3.14-7-7-7z"/>`,
    logs: `<path d="M5 6h14v2H5V6zm0 5h14v2H5v-2zm0 5h9v2H5v-2z"/>`,
  };
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="currentColor">${m[name] || ""}</svg>`;
}

function showToast(message, type = "ok") {
  const root = $("#toast-root");
  const id = "t" + Math.random().toString(36).slice(2);
  const tone = type === "ok" ? "bg-neutral-900 text-white" :
               type === "warn" ? "bg-amber-600 text-white" :
               "bg-rose-600 text-white";

  root.insertAdjacentHTML(
    "beforeend",
    `<div id="${id}" class="rounded-2xl shadow-soft ring-1 ring-black/10 px-3 py-2 ${tone} backdrop-blur-sm">
       <div class="text-sm">${message}</div>
     </div>`
  );
  setTimeout(() => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.transition = "opacity .2s ease";
    el.style.opacity = "0";
    setTimeout(() => el.remove(), 200);
  }, 2800);
}

function setLoading(btn, on) {
  if (!btn) return;
  if (on) {
    btn.dataset.prev = btn.innerHTML;
    btn.disabled = true;
    btn.classList.add("opacity-70", "cursor-progress");
    btn.innerHTML = `<span class="inline-flex items-center gap-2">${spinner(16)}<span>Выполняю…</span></span>`;
  } else {
    btn.disabled = false;
    btn.classList.remove("opacity-70", "cursor-progress");
    btn.innerHTML = btn.dataset.prev || btn.innerHTML;
  }
}

// --------------------- UI helpers -----------------------
function statePill(state, sub) {
  let tone = "bg-neutral-200 text-neutral-900 dark:bg-neutral-700 dark:text-neutral-100";
  if (state === "active" && sub === "running") tone = "bg-emerald-600 text-white";
  else if (state === "failed") tone = "bg-rose-600 text-white";
  else if (state === "activating") tone = "bg-amber-500 text-white";
  else if (state === "deactivating") tone = "bg-yellow-500 text-white";
  return `<span class="px-2 py-0.5 rounded-full text-[11px] ${tone}">${state}${sub ? " · " + sub : ""}</span>`;
}

function serviceCardHTML(s) {
  const desc = s.description || "—";
  return `
    <div class="rounded-3xl ring-1 ring-black/5 dark:ring-white/5 bg-white/70 dark:bg-neutral-900/60 backdrop-blur-xl p-3 shadow-soft transition hover:-translate-y-0.5">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <div class="font-mono text-[13px] truncate" title="${s.unit}">${s.unit}</div>
          <div class="text-sm text-gray-600 dark:text-neutral-400 truncate" title="${desc}">${desc}</div>
        </div>
        <div>${statePill(s.active_state, s.sub_state)}</div>
      </div>
      <div class="flex items-center gap-2 pt-2">
        <button data-action="start" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl ring-1 ring-black/10 dark:ring-white/10 bg-white/70 dark:bg-neutral-900/70 hover:bg-white/90 dark:hover:bg-neutral-900/90 transition inline-flex items-center gap-2">
          ${icon("play", 14)}<span>Старт</span>
        </button>
        <button data-action="stop" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl ring-1 ring-black/10 dark:ring-white/10 bg-white/70 dark:bg-neutral-900/70 hover:bg-white/90 dark:hover:bg-neutral-900/90 transition inline-flex items-center gap-2">
          ${icon("stop", 14)}<span>Стоп</span>
        </button>
        <button data-action="restart" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl ring-1 ring-black/10 dark:ring-white/10 bg-white/70 dark:bg-neutral-900/70 hover:bg-white/90 dark:hover:bg-neutral-900/90 transition inline-flex items-center gap-2">
          ${icon("restart", 14)}<span>Рестарт</span>
        </button>
        <button data-action="logs" data-unit="${s.unit}" class="ml-auto px-3 py-1.5 rounded-xl bg-brand-500 text-white hover:bg-brand-600 active:bg-brand-700 shadow-soft transition inline-flex items-center gap-2">
          ${icon("logs", 14)}<span>Логи</span>
        </button>
      </div>
    </div>
  `;
}

function skeletonCardHTML() {
  return `
    <div class="rounded-3xl ring-1 ring-black/5 dark:ring-white/5 bg-white/60 dark:bg-neutral-900/50 backdrop-blur-xl p-3 shadow-soft animate-pulse">
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0 w-full">
          <div class="h-3 w-2/3 rounded bg-black/10 dark:bg-white/10 mb-2"></div>
          <div class="h-3 w-1/3 rounded bg-black/10 dark:bg-white/10"></div>
        </div>
        <div class="h-5 w-16 rounded-full bg-black/10 dark:bg-white/10"></div>
      </div>
      <div class="flex items-center gap-2 pt-3">
        <div class="h-8 w-20 rounded-xl bg-black/10 dark:bg-white/10"></div>
        <div class="h-8 w-16 rounded-xl bg-black/10 dark:bg-white/10"></div>
        <div class="h-8 w-24 rounded-xl bg-black/10 dark:bg-white/10"></div>
        <div class="ml-auto h-8 w-20 rounded-xl bg-black/10 dark:bg-white/10"></div>
      </div>
    </div>
  `;
}

function renderSkeletons(n = 6) {
  const root = $("#services");
  root.innerHTML = "";
  for (let i = 0; i < n; i++) {
    root.insertAdjacentHTML("beforeend", skeletonCardHTML());
  }
}

function renderServices(list) {
  const root = $("#services");
  root.innerHTML = "";
  for (const s of list) {
    root.insertAdjacentHTML("beforeend", serviceCardHTML(s));
  }
}

// --------------------- Auth flow ------------------------
async function doLogin(token) {
  const { nonce } = await getJSON("/api/auth/challenge");
  const keyHex = await sha256Hex(token);
  const sig = await hmacSha256Hex(keyHex, nonce);
  const res = await postJSON("/api/auth/login", { nonce, hmac: sig });
  return res.ok === true;
}

function switchView(authenticated) {
  $("#login-view").classList.toggle("hidden", authenticated);
  $("#main-view").classList.toggle("hidden", !authenticated);
}

async function initAfterLogin() {
  renderSkeletons();
  try {
    const data = await getJSON("/api/services");
    renderServices(data.services);
  } catch (e) {
    showToast("Не удалось загрузить список сервисов", "error");
    throw e;
  }
  // status stream
  if (statusSource) statusSource.close();
  statusSource = new EventSource("/api/status/stream", { withCredentials: true });
  statusSource.addEventListener("status", (e) => {
    try {
      const payload = JSON.parse(e.data);
      renderServices(payload.services || []);
    } catch {}
  });
  statusSource.onerror = () => {}; // keep open
}

// --------------------- Logs drawer ----------------------
function openLogs(unit) {
  $("#logs-title").textContent = `Логи: ${unit}`;
  const root = $("#logs");
  const backdrop = $("#logs-backdrop");
  const panel = $("#logs-panel");
  const pre = $("#logs-pre");
  pre.textContent = "";

  root.classList.remove("hidden");
  requestAnimationFrame(() => {
    backdrop.classList.remove("opacity-0");
    panel.classList.remove("opacity-0", "translate-y-3");
  });

  if (logSource) logSource.close();
  logSource = new EventSource(`/api/logs?unit=${encodeURIComponent(unit)}&lines=200`, { withCredentials: true });
  logSource.addEventListener("log", (e) => {
    try {
      const { line } = JSON.parse(e.data);
      pre.textContent += line + "\n";
      pre.scrollTop = pre.scrollHeight;
    } catch {}
  });
  logSource.onerror = () => {}; // keep open
}

function closeLogs() {
  const root = $("#logs");
  const backdrop = $("#logs-backdrop");
  const panel = $("#logs-panel");
  backdrop.classList.add("opacity-0");
  panel.classList.add("opacity-0", "translate-y-3");
  setTimeout(() => {
    if (logSource) {
      logSource.close();
      logSource = null;
    }
    root.classList.add("hidden");
  }, 180);
}

// --------------------- Events ---------------------------
window.addEventListener("DOMContentLoaded", () => {
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const token = $("#token-input").value.trim();
    $("#login-error").classList.add("hidden");

    const btn = e.submitter || $("#login-form button[type=submit]");
    try {
      setLoading(btn, true);
      const ok = await doLogin(token);
      if (!ok) throw new Error("bad token");
      switchView(true);
      await initAfterLogin();
      showToast("Вход выполнен");
    } catch (e) {
      console.error("Login error:", e);
      $("#login-error").classList.remove("hidden");
      showToast("Неверный токен", "error");
    } finally {
      setLoading(btn, false);
    }
  });

  $("#logout-btn").addEventListener("click", async () => {
    try {
      await postJSON("/api/auth/logout", {});
      showToast("Вы вышли из аккаунта", "ok");
    } catch {
      // even if request fails, force logout UI
      showToast("Сессия завершена локально", "warn");
    } finally {
      if (statusSource) statusSource.close();
      if (logSource) logSource.close();
      switchView(false);
    }
  });

  $("#refresh-btn").addEventListener("click", async () => {
    renderSkeletons(6);
    try {
      const data = await getJSON("/api/services");
      renderServices(data.services);
      showToast("Обновлено");
    } catch {
      showToast("Ошибка обновления", "error");
    }
  });

  $("#services").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    const action = btn.getAttribute("data-action");
    const unit = btn.getAttribute("data-unit");
    if (action === "logs") {
      openLogs(unit);
      return;
    }
    try {
      setLoading(btn, true);
      await postJSON(`/api/service/${encodeURIComponent(unit)}/${action}`, {});
      showToast(`${unit}: ${action} отправлен`);
    } catch (err) {
      console.error(err);
      showToast(`Ошибка: ${String(err).slice(0, 200)}`, "error");
    } finally {
      setLoading(btn, false);
    }
  });

  $("#logs-close").addEventListener("click", closeLogs);
});
