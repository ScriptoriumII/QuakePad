// QuakePad — panneau latéral : notes à onglets, sauvegarde automatique, rechercher/remplacer.
"use strict";

const $ = (sel) => document.querySelector(sel);
const ed = $("#editor");
const tabsEl = $("#tabs");
const menu = $("#menu");
const findbar = $("#findbar");
const findInput = $("#find");
const replaceInput = $("#replace");

// ------------------------------------------------------------------
// Stockage (chrome.storage.local, avec repli localStorage pour tester hors extension)
// ------------------------------------------------------------------
const hasChrome = typeof chrome !== "undefined" && chrome.storage && chrome.storage.local;
const store = {
  async get(keys) {
    if (hasChrome) return chrome.storage.local.get(keys);
    const out = {};
    for (const k of keys) {
      try { const v = localStorage.getItem("qp:" + k); if (v !== null) out[k] = JSON.parse(v); } catch {}
    }
    return out;
  },
  async set(obj) {
    if (hasChrome) return chrome.storage.local.set(obj);
    for (const [k, v] of Object.entries(obj)) {
      try { localStorage.setItem("qp:" + k, JSON.stringify(v)); } catch {}
    }
  },
};

const WRITER = Math.random().toString(36).slice(2); // identifie ce panneau (multi-fenêtres)
const DEFAULT_PREFS = { wrap: true, zoom: 0, theme: "auto" };
let notes = [];
let currentId = null;
let prefs = { ...DEFAULT_PREFS };
let saveTimer = null;
let dirty = false;

const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const current = () => notes.find((n) => n.id === currentId) || notes[0];

function newNote(content = "", title = "") {
  const n = { id: uid(), title, autoTitle: !title, content, cursor: 0, updated: Date.now() };
  return n;
}

function displayTitle(n) {
  if (!n.autoTitle && n.title) return n.title;
  const first = (n.content.split("\n").find((l) => l.trim()) || "").trim();
  if (first) return first.length > 28 ? first.slice(0, 27) + "…" : first;
  return "Note " + (notes.indexOf(n) + 1);
}

// ------------------------------------------------------------------
// Chargement / sauvegarde
// ------------------------------------------------------------------
async function load() {
  const data = await store.get(["notes", "current", "prefs"]);
  notes = Array.isArray(data.notes) && data.notes.length ? data.notes : [newNote()];
  currentId = notes.some((n) => n.id === data.current) ? data.current : notes[0].id;
  prefs = { ...DEFAULT_PREFS, ...(data.prefs || {}) };
}

function scheduleSave() {
  dirty = true;
  $("#st-saved").textContent = "Enregistrement…";
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSave, 400);
}

async function flushSave() {
  clearTimeout(saveTimer);
  const n = current();
  if (n) n.cursor = ed.selectionStart;
  await store.set({ notes, current: currentId, prefs, writer: WRITER, rev: Date.now() });
  dirty = false;
  const t = new Date();
  $("#st-saved").textContent = `Enregistré ${t.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}`;
}

// Synchronisation si le panneau est ouvert dans une autre fenêtre Chrome.
if (hasChrome) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !changes.notes || (changes.writer && changes.writer.newValue === WRITER)) return;
    if (dirty) return; // nos modifications en cours restent prioritaires
    notes = changes.notes.newValue || notes;
    if (!notes.some((n) => n.id === currentId)) currentId = notes[0] && notes[0].id;
    const keepSel = document.activeElement === ed ? [ed.selectionStart, ed.selectionEnd] : null;
    renderTabs();
    showNote(false);
    if (keepSel) ed.setSelectionRange(...keepSel);
  });
}

// ------------------------------------------------------------------
// Rendu
// ------------------------------------------------------------------
function renderTabs() {
  tabsEl.textContent = "";
  notes.forEach((n, i) => {
    const b = document.createElement("div");
    b.className = "tab";
    b.setAttribute("role", "tab");
    b.setAttribute("aria-selected", String(n.id === currentId));
    b.tabIndex = 0;
    b.draggable = true;
    b.dataset.id = n.id;
    b.title = (i < 9 ? `Alt+${i + 1} · ` : "") + "Double-clic pour renommer";
    const name = document.createElement("span");
    name.className = "name";
    name.textContent = displayTitle(n);
    const close = document.createElement("span");
    close.className = "close";
    close.textContent = "✕";
    close.title = "Supprimer la note";
    close.addEventListener("click", (e) => { e.stopPropagation(); deleteNote(n.id); });
    b.append(name, close);
    b.addEventListener("click", () => switchTo(n.id));
    b.addEventListener("auxclick", (e) => { if (e.button === 1) deleteNote(n.id); });
    b.addEventListener("dblclick", () => startRename(n.id));
    b.addEventListener("keydown", (e) => { if (e.key === "Enter") switchTo(n.id); });
    // Glisser-déposer pour réordonner
    b.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/qp-tab", n.id));
    b.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("text/qp-tab")) e.preventDefault(); });
    b.addEventListener("drop", (e) => {
      const from = e.dataTransfer.getData("text/qp-tab");
      if (!from || from === n.id) return;
      e.preventDefault();
      const src = notes.findIndex((x) => x.id === from);
      const [moved] = notes.splice(src, 1);
      notes.splice(notes.findIndex((x) => x.id === n.id), 0, moved);
      renderTabs();
      scheduleSave();
    });
    tabsEl.appendChild(b);
  });
  const active = tabsEl.querySelector('[aria-selected="true"]');
  if (active) active.scrollIntoView({ block: "nearest", inline: "nearest" });
}

function refreshCurrentTabTitle() {
  const el = tabsEl.querySelector(`[data-id="${currentId}"] .name`);
  if (el) el.textContent = displayTitle(current());
}

function showNote(focus = true) {
  const n = current();
  if (!n) return;
  ed.value = n.content;
  const pos = Math.min(n.cursor || 0, n.content.length);
  ed.setSelectionRange(pos, pos);
  if (focus) ed.focus();
  updateStatus();
}

function applyPrefs() {
  document.documentElement.style.setProperty("--font-size", `${13 + prefs.zoom}px`);
  ed.classList.toggle("nowrap", !prefs.wrap);
  if (prefs.theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = prefs.theme;
  menu.querySelector('[data-cmd="wrap"]').setAttribute("aria-checked", String(prefs.wrap));
  $("#theme-name").textContent = { auto: "système", dark: "sombre", light: "clair" }[prefs.theme];
  updateStatus();
}

function updateStatus() {
  const before = ed.value.slice(0, ed.selectionStart);
  const ln = before.split("\n").length;
  const col = ed.selectionStart - before.lastIndexOf("\n");
  $("#st-pos").textContent = `Ln ${ln}, Col ${col}`;
  $("#st-len").textContent = `${ed.value.length} car.`;
  $("#st-zoom").textContent = `${Math.round(((13 + prefs.zoom) / 13) * 100)} %`;
}

// ------------------------------------------------------------------
// Opérations sur les notes
// ------------------------------------------------------------------
function switchTo(id) {
  const n = current();
  if (n) n.cursor = ed.selectionStart;
  currentId = id;
  renderTabs();
  showNote();
  scheduleSave();
}

function addNote(content = "", title = "") {
  const n = newNote(content, title);
  const idx = notes.findIndex((x) => x.id === currentId);
  notes.splice(idx + 1, 0, n);
  switchTo(n.id);
  return n;
}

function deleteNote(id) {
  const n = notes.find((x) => x.id === id);
  if (!n) return;
  if (n.content.trim() && !confirm(`Supprimer définitivement « ${displayTitle(n)} » ?`)) return;
  const idx = notes.indexOf(n);
  notes.splice(idx, 1);
  if (!notes.length) notes.push(newNote());
  if (currentId === id) currentId = notes[Math.max(0, idx - 1)].id;
  renderTabs();
  showNote();
  scheduleSave();
}

function startRename(id) {
  const tab = tabsEl.querySelector(`[data-id="${id}"]`);
  const n = notes.find((x) => x.id === id);
  if (!tab || !n) return;
  const input = document.createElement("input");
  input.value = displayTitle(n);
  input.setAttribute("aria-label", "Nom de la note");
  tab.querySelector(".name").replaceWith(input);
  input.focus();
  input.select();
  let done = false;
  const finish = (ok) => {
    if (done) return;
    done = true;
    if (ok) {
      const v = input.value.trim();
      n.title = v;
      n.autoTitle = !v; // vide => titre automatique (1re ligne)
      scheduleSave();
    }
    renderTabs();
    ed.focus();
  };
  input.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Enter") finish(true);
    if (e.key === "Escape") finish(false);
  });
  input.addEventListener("blur", () => finish(true));
}

// Insertion qui conserve l'historique Ctrl+Z du textarea.
function insertText(text, start = ed.selectionStart, end = ed.selectionEnd) {
  ed.focus();
  ed.setSelectionRange(start, end);
  if (!document.execCommand("insertText", false, text)) {
    ed.setRangeText(text, start, end, "end");
    ed.dispatchEvent(new Event("input"));
  }
}

function insertDate() {
  const d = new Date();
  const p = (x) => String(x).padStart(2, "0");
  insertText(`${p(d.getHours())}:${p(d.getMinutes())} ${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()}`);
}

// ------------------------------------------------------------------
// Import / export
// ------------------------------------------------------------------
function download(name, text) {
  const blob = new Blob([text.replace(/\n/g, "\r\n")], { type: "text/plain;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name.replace(/[\\/:*?"<>|]+/g, "_").slice(0, 80) || "note";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function exportCurrent() {
  const n = current();
  download(displayTitle(n).replace(/…$/, "") + ".txt", n.content);
}

function exportAll() {
  const stamp = new Date().toISOString().slice(0, 10);
  const body = notes.map((n) => `===== ${displayTitle(n)} =====\n${n.content}`).join("\n\n");
  download(`quakepad-notes-${stamp}.txt`, body);
}

$("#file-input").addEventListener("change", async (e) => {
  for (const file of e.target.files) {
    const text = (await file.text()).replace(/\r\n?/g, "\n");
    addNote(text, file.name.replace(/\.[^.]+$/, ""));
  }
  e.target.value = "";
});

// ------------------------------------------------------------------
// Rechercher / remplacer
// ------------------------------------------------------------------
function buildRegex() {
  const q = findInput.value;
  if (!q) return null;
  let src = $("#opt-regex").checked ? q : q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if ($("#opt-word").checked) src = `\\b(?:${src})\\b`;
  try {
    return new RegExp(src, "g" + ($("#opt-case").checked ? "" : "i") + "m");
  } catch {
    return null;
  }
}

function markFound(ok) { findInput.classList.toggle("notfound", !ok); }

// Fait défiler le textarea jusqu'à un index (div miroir pour mesurer la position réelle).
const mirror = document.createElement("div");
function scrollToIndex(idx) {
  const cs = getComputedStyle(ed);
  Object.assign(mirror.style, {
    position: "absolute", visibility: "hidden", top: "0", left: "-9999px",
    width: ed.clientWidth + "px", font: cs.font, lineHeight: cs.lineHeight, padding: cs.padding,
    whiteSpace: cs.whiteSpace, overflowWrap: cs.overflowWrap, tabSize: cs.tabSize, boxSizing: "border-box",
  });
  mirror.textContent = ed.value.slice(0, idx) + "​";
  document.body.appendChild(mirror);
  const y = mirror.scrollHeight;
  mirror.remove();
  if (y < ed.scrollTop + 40 || y > ed.scrollTop + ed.clientHeight - 20) {
    ed.scrollTop = Math.max(0, y - ed.clientHeight / 2);
  }
}

function findNext(backward = false) {
  const re = buildRegex();
  if (!re) { markFound(!findInput.value); return false; }
  const text = ed.value;
  const matches = [...text.matchAll(re)].filter((m) => m[0].length > 0);
  if (!matches.length) { markFound(false); return false; }
  let m;
  if (backward) {
    const before = matches.filter((x) => x.index < ed.selectionStart);
    m = before.length ? before[before.length - 1] : matches[matches.length - 1];
  } else {
    m = matches.find((x) => x.index >= ed.selectionEnd) || matches[0];
  }
  ed.setSelectionRange(m.index, m.index + m[0].length);
  scrollToIndex(m.index);
  markFound(true);
  updateStatus();
  return true;
}

function replaceOne() {
  const re = buildRegex();
  if (!re) return;
  const sel = ed.value.slice(ed.selectionStart, ed.selectionEnd);
  const single = new RegExp(`^(?:${re.source})$`, re.flags.replace("g", ""));
  if (sel && single.test(sel)) {
    const repl = $("#opt-regex").checked ? sel.replace(single, replaceInput.value) : replaceInput.value;
    insertText(repl);
    replaceInput.focus();
  }
  findNext();
}

function replaceAll() {
  const re = buildRegex();
  if (!re) return;
  const count = [...ed.value.matchAll(re)].length;
  if (!count) { markFound(false); return; }
  const repl = $("#opt-regex").checked ? replaceInput.value : () => replaceInput.value;
  const out = ed.value.replace(re, repl);
  insertText(out, 0, ed.value.length); // une seule étape d'annulation
  $("#st-saved").textContent = `${count} remplacement(s)`;
  markFound(true);
}

function openFind(withReplace) {
  const sel = ed.value.slice(ed.selectionStart, ed.selectionEnd);
  if (sel && !sel.includes("\n")) findInput.value = sel;
  $("#replace-row").hidden = !withReplace;
  findbar.hidden = false;
  findInput.focus();
  findInput.select();
}

function closeFind() {
  findbar.hidden = true;
  ed.focus();
}

$("#find-next").addEventListener("click", () => findNext());
$("#find-prev").addEventListener("click", () => findNext(true));
$("#find-close").addEventListener("click", closeFind);
$("#replace-one").addEventListener("click", replaceOne);
$("#replace-all").addEventListener("click", replaceAll);
findInput.addEventListener("input", () => markFound(true));
findInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); findNext(e.shiftKey); }
});
replaceInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); e.ctrlKey ? replaceAll() : replaceOne(); }
});
findbar.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); closeFind(); } });

// ------------------------------------------------------------------
// Commandes (menu + raccourcis)
// ------------------------------------------------------------------
const commands = {
  new: () => addNote(),
  import: () => $("#file-input").click(),
  export: exportCurrent,
  exportAll,
  find: () => openFind(false),
  replace: () => openFind(true),
  date: insertDate,
  wrap: () => { prefs.wrap = !prefs.wrap; applyPrefs(); scheduleSave(); },
  theme: () => {
    prefs.theme = { auto: "dark", dark: "light", light: "auto" }[prefs.theme] || "auto";
    applyPrefs(); scheduleSave();
  },
  zoomIn: () => { prefs.zoom = Math.min(30, prefs.zoom + 1); applyPrefs(); scheduleSave(); },
  zoomOut: () => { prefs.zoom = Math.max(-5, prefs.zoom - 1); applyPrefs(); scheduleSave(); },
  zoomReset: () => { prefs.zoom = 0; applyPrefs(); scheduleSave(); },
  rename: () => startRename(currentId),
  close: () => deleteNote(currentId),
  shortcuts: () => hasChrome && chrome.tabs.create({ url: "chrome://extensions/shortcuts" }),
};

function toggleMenu(show = menu.hidden) {
  menu.hidden = !show;
  $("#btn-menu").setAttribute("aria-expanded", String(show));
  if (show) menu.querySelector("button").focus();
}

$("#btn-new").addEventListener("click", commands.new);
$("#btn-menu").addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(); });
menu.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-cmd]");
  if (!b) return;
  toggleMenu(false);
  commands[b.dataset.cmd]();
});
document.addEventListener("click", (e) => {
  if (!menu.hidden && !menu.contains(e.target)) toggleMenu(false);
});

document.addEventListener("keydown", (e) => {
  const k = e.key.toLowerCase();
  const ctrl = e.ctrlKey || e.metaKey;
  let cmd = null;
  if (ctrl && !e.altKey && k === "f") cmd = "find";
  else if (ctrl && !e.altKey && k === "h") cmd = "replace";
  else if (ctrl && !e.altKey && k === "s") cmd = e.shiftKey ? "exportAll" : "export";
  else if (ctrl && !e.altKey && k === "o") cmd = "import";
  else if (e.key === "F5") cmd = "date";
  else if (e.key === "F2") cmd = "rename";
  else if (e.key === "F3") { e.preventDefault(); if (findInput.value) findNext(e.shiftKey); else openFind(false); return; }
  else if (e.altKey && !ctrl && k === "n") cmd = "new";
  else if (e.altKey && !ctrl && k === "w") cmd = "close";
  else if (e.altKey && !ctrl && k === "z") cmd = "wrap";
  else if ((e.altKey || ctrl) && (e.key === "=" || e.key === "+")) cmd = "zoomIn";
  else if ((e.altKey || ctrl) && e.key === "-") cmd = "zoomOut";
  else if ((e.altKey || ctrl) && e.key === "0") cmd = "zoomReset";
  else if (e.altKey && !ctrl && /^[1-9]$/.test(e.key)) {
    const i = e.key === "9" ? notes.length - 1 : Number(e.key) - 1;
    if (notes[i]) { e.preventDefault(); switchTo(notes[i].id); }
    return;
  } else if (e.altKey && (e.key === "PageDown" || e.key === "PageUp")) {
    const i = notes.findIndex((n) => n.id === currentId);
    const j = (i + (e.key === "PageDown" ? 1 : -1) + notes.length) % notes.length;
    e.preventDefault();
    switchTo(notes[j].id);
    return;
  } else if (e.key === "Escape" && !menu.hidden) { toggleMenu(false); return; }
  if (cmd) { e.preventDefault(); commands[cmd](); }
});

// Tabulation = caractère tab (et Maj+Tab retire une indentation en début de ligne)
ed.addEventListener("keydown", (e) => {
  if (e.key !== "Tab" || e.ctrlKey || e.altKey) return;
  e.preventDefault();
  if (!e.shiftKey) { insertText("\t"); return; }
  const lineStart = ed.value.lastIndexOf("\n", ed.selectionStart - 1) + 1;
  const m = ed.value.slice(lineStart).match(/^(\t| {1,4})/);
  if (m) {
    const s = ed.selectionStart, en = ed.selectionEnd;
    insertText("", lineStart, lineStart + m[0].length);
    ed.setSelectionRange(Math.max(lineStart, s - m[0].length), Math.max(lineStart, en - m[0].length));
  }
});

ed.addEventListener("input", () => {
  const n = current();
  n.content = ed.value;
  n.updated = Date.now();
  if (n.autoTitle) refreshCurrentTabTitle();
  updateStatus();
  scheduleSave();
});
["keyup", "click", "select"].forEach((ev) => ed.addEventListener(ev, updateStatus));

// Glisser un fichier texte sur le panneau => nouvelle note
document.addEventListener("dragover", (e) => { if (e.dataTransfer.types.includes("Files")) e.preventDefault(); });
document.addEventListener("drop", async (e) => {
  if (!e.dataTransfer.files.length) return;
  e.preventDefault();
  for (const f of e.dataTransfer.files) {
    addNote((await f.text()).replace(/\r\n?/g, "\n"), f.name.replace(/\.[^.]+$/, ""));
  }
});

// Ne rien perdre à la fermeture du panneau
document.addEventListener("visibilitychange", () => { if (document.hidden && dirty) flushSave(); });
window.addEventListener("pagehide", () => { if (dirty) flushSave(); });

// ------------------------------------------------------------------
// Lien avec le service worker (bascule Alt+Q)
// ------------------------------------------------------------------
async function connectToBackground() {
  if (!hasChrome || !chrome.windows) return;
  const win = await chrome.windows.getCurrent();
  const port = chrome.runtime.connect({ name: `panel:${win.id}` });
  port.onMessage.addListener(async (msg) => {
    if (msg && msg.type === "close") {
      if (dirty) await flushSave();
      window.close();
    }
  });
}

// ------------------------------------------------------------------
(async function init() {
  await load();
  applyPrefs();
  renderTabs();
  showNote();
  $("#st-saved").textContent = "Prêt";
  connectToBackground().catch(console.error);
})();
