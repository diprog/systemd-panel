"use strict";

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
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}

// --------------------- UI helpers -----------------------
function badge(state, sub) {
  let color = "bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-gray-100";
  if (state === "active" && sub === "running") color = "bg-green-600 text-white";
  else if (state === "failed") color = "bg-red-600 text-white";
  else if (state === "activating") color = "bg-blue-600 text-white";
  else if (state === "deactivating") color = "bg-yellow-500 text-white";
  return `<span class="px-2 py-0.5 rounded-lg text-xs ${color}">${state}${sub ? " · " + sub : ""}</span>`;
}

function renderServices(list) {
  const root = $("#services");
  root.innerHTML = "";
  for (const s of list) {
    const desc = s.description || "—";
    root.insertAdjacentHTML(
      "beforeend",
      `
      <div class="rounded-2xl border p-3 bg-white/70 dark:bg-gray-800/70 backdrop-blur space-y-2">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-mono text-sm truncate" title="${s.unit}">${s.unit}</div>
            <div class="text-sm text-gray-500 dark:text-gray-400 truncate" title="${desc}">${desc}</div>
          </div>
          <div>${badge(s.active_state, s.sub_state)}</div>
        </div>
        <div class="flex items-center gap-2">
          <button data-action="start" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl border hover:bg-gray-100 dark:hover:bg-gray-800">Старт</button>
          <button data-action="stop" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl border hover:bg-gray-100 dark:hover:bg-gray-800">Стоп</button>
          <button data-action="restart" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl border hover:bg-gray-100 dark:hover:bg-gray-800">Рестарт</button>
          <button data-action="logs" data-unit="${s.unit}" class="px-3 py-1.5 rounded-xl border hover:bg-gray-100 dark:hover:bg-gray-800 ml-auto">Логи</button>
        </div>
      </div>
      `
    );
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
  const data = await getJSON("/api/services");
  renderServices(data.services);
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
  $("#logs").classList.remove("hidden");
  const pre = $("#logs-pre");
  pre.textContent = "";

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
  $("#logs").classList.add("hidden");
  if (logSource) {
    logSource.close();
    logSource = null;
  }
}

// --------------------- Events ---------------------------
window.addEventListener("DOMContentLoaded", () => {
  $("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const token = $("#token-input").value.trim();
  $("#login-error").classList.add("hidden");

  try {
    const ok = await doLogin(token);
    if (!ok) throw new Error("bad token");
    switchView(true);
    await initAfterLogin();
  } catch (e) {
    console.error("Login error:", e);
    $("#login-error").classList.remove("hidden");
  }
});

  $("#logout-btn").addEventListener("click", async () => {
    try {
      await postJSON("/api/auth/logout", {});
    } finally {
      if (statusSource) statusSource.close();
      if (logSource) logSource.close();
      switchView(false);
    }
  });

  $("#refresh-btn").addEventListener("click", async () => {
    const data = await getJSON("/api/services");
    renderServices(data.services);
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
      await postJSON(`/api/service/${encodeURIComponent(unit)}/${action}`, {});
    } catch (err) {
      alert("Ошибка: " + err);
    }
  });

  $("#logs-close").addEventListener("click", closeLogs);
});
