/* global document, WebSocket, fetch */
const $ = (sel) => document.querySelector(sel);

const loginForm = $("#login-form");
const main = $("#main");
const serviceList = $("#service-list");
const logModal = $("#log-modal");
const logContent = $("#log-content");
const logTitle = $("#log-title");
const closeLogBtn = $("#close-log");

let token = localStorage.getItem("token") || "";

start();

/* ---------- auth ---------- */
async function login() {
  const res = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token }),
  });
  const ok = (await res.json()).ok;
  if (!ok) {
    $("#login-error").classList.remove("hidden");
    return false;
  }
  localStorage.setItem("token", token);
  loginForm.classList.add("hidden");
  main.classList.remove("hidden");
  refreshServices();
  return true;
}

/* ---------- services ---------- */
async function refreshServices() {
  const res = await fetch("/api/services");
  const list = await res.json();
  serviceList.innerHTML = "";
  list.forEach(renderService);
}

function renderService(svc) {
  const div = document.createElement("div");
  div.className =
    "flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 border rounded dark:border-neutral-700";
  const info = document.createElement("div");
  info.innerHTML = `
    <div class="font-bold">${svc.name}</div>
    <div class="text-sm">${svc.active ? "active" : "inactive"} (${svc.sub})</div>`;
  const actions = document.createElement("div");
  actions.className = "flex gap-2";
  ["start", "stop", "restart"].forEach((act) => {
    const btn = document.createElement("button");
    btn.textContent = act;
    btn.className =
      "px-3 py-1 rounded bg-blue-600 text-white text-sm capitalize";
    btn.onclick = async () => {
      await fetch(`/api/services/${svc.name}/${act}`, { method: "POST" });
      setTimeout(refreshServices, 500);
    };
    actions.appendChild(btn);
  });
  const logBtn = document.createElement("button");
  logBtn.textContent = "logs";
  logBtn.className =
    "px-3 py-1 rounded bg-neutral-600 text-white text-sm";
  logBtn.onclick = () => openLogs(svc.name);
  actions.appendChild(logBtn);
  div.append(info, actions);
  serviceList.appendChild(div);
}

/* ---------- logs ---------- */
let ws = null;
function openLogs(unit) {
  logTitle.textContent = unit;
  logContent.textContent = "";
  logModal.classList.remove("hidden");
  logModal.classList.add("flex");
  ws = new WebSocket(`wss://${location.host}/ws/logs/${unit}`);
  ws.onmessage = (e) => (logContent.textContent += e.data + "\n");
  ws.onclose = () => (logContent.textContent += "----- disconnected -----\n");
}

closeLogBtn.onclick = () => {
  ws?.close();
  logModal.classList.add("hidden");
  logModal.classList.remove("flex");
};

/* ---------- init ---------- */
async function start() {
  if (token) {
    if (await login()) return;
  }
  loginForm.classList.remove("hidden");
  loginForm.onsubmit = async (e) => {
    e.preventDefault();
    token = $("#token").value.trim();
    if (token) await login();
  };
}