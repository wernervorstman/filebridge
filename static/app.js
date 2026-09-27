'use strict';
/* FileBridge – browser interface */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(name, body = {}) {
  const r = await fetch('/api/' + name, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Token': window.FB_TOKEN },
    body: JSON.stringify(body),
  });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || 'Unknown error');
  return j;
}

function fmtSize(n) {
  if (n == null) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + ' ' + u[i];
}
function fmtDate(t) {
  if (!t) return '';
  return new Date(t * 1000).toLocaleString(undefined, { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}
const typeLabel = e => e.dir ? 'Folder' : (e.ext ? e.ext.toUpperCase() + ' file' : 'File');
const joinPath = (dir, name) => (dir.endsWith('/') ? dir : dir + '/') + name;
const parentOf = p => { const q = p.replace(/\/+$/, ''); const i = q.lastIndexOf('/'); return i <= 0 ? '/' : q.slice(0, i); };
const baseName = p => p.replace(/[\\/]+$/, '').split(/[\\/]/).pop();
const modeOct = m => m == null ? '' : m.toString(8).padStart(4, '0');
function modeText(m) {
  if (m == null) return '';
  const t = (r, w, x, sp, c) => (m & r ? 'r' : '-') + (m & w ? 'w' : '-') + (m & sp ? (m & x ? c : c.toUpperCase()) : (m & x ? 'x' : '-'));
  return t(0o400, 0o200, 0o100, 0o4000, 's') + t(0o40, 0o20, 0o10, 0o2000, 's') + t(0o4, 0o2, 0o1, 0o1000, 't');
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* app window: fall back */ }
  const ta = document.createElement('textarea');
  ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.append(ta); ta.select();
  const ok = document.execCommand('copy');
  ta.remove();
  return ok;
}
const store = {
  get(k, d) { try { const v = localStorage.getItem('fb.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem('fb.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
};

const SVG = p => `<svg class="bi" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const BTN_ICON = {
  up: SVG('<path d="M12 19V5M6 11l6-6 6 6"/>'),
  refresh: SVG('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>'),
  folder: SVG('<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>'),
  bookmark: SVG('<path d="M6 4h12v16l-6-4-6 4z"/>'),
};
const ICON = {
  dir: '<svg class="ico ico-dir" viewBox="0 0 16 16"><path fill="currentColor" d="M1.5 3.5A1.5 1.5 0 0 1 3 2h3.2l1.6 1.6H13A1.5 1.5 0 0 1 14.5 5v7.5A1.5 1.5 0 0 1 13 14H3a1.5 1.5 0 0 1-1.5-1.5z"/></svg>',
  file: '<svg class="ico ico-file" viewBox="0 0 16 16"><path fill="none" stroke="currentColor" stroke-width="1.2" d="M4 1.6h5.2L12.4 5v9.4H4z M9 1.6V5h3.4"/></svg>',
  up: '<svg class="ico ico-dir" viewBox="0 0 16 16"><path fill="none" stroke="currentColor" stroke-width="1.6" d="M8 13V3.5M4 7l4-4 4 4"/></svg>',
};

/* ---------------------------------------------------------------- state */
const S = {
  sites: [],
  plugins: [],
  status: { connected: false },
  home: '/',
  ignore: [],
  active: null,
  callbacks: {},   // job id -> fn(job)
};
const currentSite = () => S.sites.find(s => s.id === $('#siteSelect').value) || null;

/* ---------------------------------------------------------------- toasts, menus, modals */
function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 6000 : 3000);
}

function showMenu(x, y, items) {
  const m = $('#menu');
  m.innerHTML = '';
  for (const it of items) {
    if (!it) continue;
    const d = document.createElement('div');
    if (it.sep) d.className = 'sep';
    else if (it.header) { d.className = 'hd'; d.textContent = it.header; }
    else {
      d.className = 'mi' + (it.disabled ? ' disabled' : '') + (it.danger ? ' danger' : '');
      d.innerHTML = `<span>${esc(it.label)}</span>${it.hint ? `<span class="hint">${esc(it.hint)}</span>` : ''}`;
      d.onclick = () => { hideMenu(); it.action(); };
    }
    m.append(d);
  }
  m.hidden = false;
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(4, Math.min(x, innerWidth - r.width - 8)) + 'px';
  m.style.top = Math.max(4, Math.min(y, innerHeight - r.height - 8)) + 'px';
}
function hideMenu() { $('#menu').hidden = true; }
document.addEventListener('mousedown', e => { if (!e.target.closest('#menu')) hideMenu(); });
window.addEventListener('blur', hideMenu);

/**
 * Show a modal. Resolves with {value, el} when a button is pressed (value null on Esc/cancel).
 * A button with `keep: true` calls onClick(el) without closing.
 */
function modal({ title, body, buttons = [{ label: 'OK', value: 'ok', primary: true }], size = '', onOpen }) {
  return new Promise(resolve => {
    const ov = document.createElement('div');
    ov.className = 'overlay';
    ov.innerHTML = `<div class="modal ${size}"><h2>${esc(title)}</h2><div class="mbody">${body}</div><div class="mfoot"></div></div>`;
    const el = $('.modal', ov);
    const close = value => { ov.remove(); document.removeEventListener('keydown', onKey, true); resolve({ value, el }); };
    for (const b of buttons) {
      const btn = document.createElement('button');
      btn.textContent = b.label;
      if (b.primary) btn.className = 'primary';
      if (b.danger) btn.className = 'danger';
      if (b.id) btn.id = b.id;
      if (b.left) btn.style.marginRight = 'auto';
      btn.onclick = () => (b.onClick ? b.onClick(el, close) : close(b.value ?? null));
      $('.mfoot', el).append(btn);
    }
    function onKey(e) {
      if (ov !== $('#modalRoot').lastElementChild) return;
      if (e.key === 'Escape') { e.stopPropagation(); close(null); }
      if (e.key === 'Enter' && e.target.matches('input:not([type=checkbox]):not([type=radio])') && el.contains(e.target) && !e.target.dataset.noenter) {
        const p = buttons.find(b => b.primary);
        if (p) { e.preventDefault(); p.onClick ? p.onClick(el, close) : close(p.value ?? 'ok'); }
      }
    }
    document.addEventListener('keydown', onKey, true);
    $('#modalRoot').append(ov);
    if (onOpen) onOpen(el, close);
    const first = $('input:not([type=checkbox]), select', el);
    if (first) { first.focus(); if (first.select) first.select(); }
  });
}
async function askText(title, label, value = '', type = 'text') {
  const { value: v, el } = await modal({
    title,
    body: `<label class="field">${esc(label)}<input id="askInput" type="${type}" value="${esc(value)}"></label>`,
    buttons: [{ label: 'Cancel', value: null }, { label: 'OK', value: 'ok', primary: true }],
  });
  return v ? $('#askInput', el).value : null;
}
async function confirmBox(title, message, okLabel = 'OK', danger = false) {
  const { value } = await modal({
    title, body: `<p>${message}</p>`,
    buttons: [{ label: 'Cancel', value: null }, { label: okLabel, value: 'ok', primary: !danger, danger }],
  });
  return value === 'ok';
}
function showResult(title, text) {
  modal({ title, body: `<pre class="result">${esc(text)}</pre>`, size: 'mid', buttons: [{ label: 'Close', value: null, primary: true }] });
}

/* ---------------------------------------------------------------- panes */
class Pane {
  constructor(side) {
    this.side = side;
    this.el = $(side === 'local' ? '#paneLocal' : '#paneRemote');
    this.path = '';
    this.entries = [];
    this.sel = new Set();
    this.anchor = null;
    this.sortKey = store.get(side + '.sortKey', 'name');
    this.sortDir = store.get(side + '.sortDir', 1);
    this.filter = '';
    this.showHidden = store.get(side + '.hidden', false);
    this.build();
  }
  get remote() { return this.side === 'remote'; }
  /** Parent folder, or null at the top (/ or a drive like C:\). */
  get parentPath() { return this.remote ? (this.path && this.path !== '/' ? parentOf(this.path) : null) : this.localParent; }
  get other() { return this.remote ? PL : PR; }

  build() {
    const r = this.remote;
    this.el.innerHTML = `
      <div class="pane-head">
        <span class="pane-title">${r ? 'Server' : 'Local'}</span>
        <button class="icon" data-a="up" title="Parent folder (⌘↑)" aria-label="Parent folder">${BTN_ICON.up}</button>
        <input class="path" spellcheck="false" autocomplete="off">
        ${r ? '' : `<button class="icon" data-a="pick" title="Choose a folder on this computer" aria-label="Choose folder">${BTN_ICON.folder}</button>`}
        <button class="icon" data-a="refresh" title="Refresh – reload this folder" aria-label="Refresh">${BTN_ICON.refresh}</button>
        <button class="icon" data-a="bookmarks" title="Bookmarks" aria-label="Bookmarks">${BTN_ICON.bookmark}</button>
      </div>
      <div class="toolbar">
        <button data-a="transfer" class="primary" title="${r ? 'Download selected to the local folder' : 'Upload selected to the server folder'}">${r ? '← Download' : 'Upload →'}</button>
        <button data-a="mkdir">New folder</button>
        <button data-a="rename">Rename</button>
        <button data-a="move">Move to…</button>
        <button data-a="delete" class="danger">Delete</button>
        <button data-a="chmod">Permissions</button>
        <button data-a="types" title="Select all files of a type">Select type ▾</button>
        <button data-a="permsel" title="Select all items with a certain permission">Select permission ▾</button>
        <button data-a="selnew" title="Compare with the folder open on the other side and select what is missing or changed">Select new ▾</button>
        <input class="filter" placeholder="Filter…" spellcheck="false">
        <label class="chk" title="Show hidden files"><input type="checkbox" class="hidden-toggle"> Hidden</label>
      </div>
      <div class="list" tabindex="0">
        <table>
          <thead><tr>
            <th class="c-chk"><input type="checkbox" class="all" title="Select all"></th>
            <th data-k="name" class="c-name">Name</th>
            <th data-k="type" class="c-type">Type</th>
            <th data-k="size" class="c-size num">Size</th>
            <th data-k="mtime" class="c-date">Modified</th>
            <th data-k="perms" class="c-perm">Permissions</th>
          </tr></thead>
          <tbody></tbody>
        </table>
        <div class="empty" hidden></div>
      </div>
      <div class="pane-foot"><span class="count"></span><span class="selinfo"></span><span class="diffinfo"></span></div>`;

    this.list = $('.list', this.el);
    this.tbody = $('tbody', this.el);
    $('.hidden-toggle', this.el).checked = this.showHidden;

    this.el.addEventListener('mousedown', () => setActive(this));
    $('.pane-head', this.el).addEventListener('click', e => this.onButton(e));
    $('.toolbar', this.el).addEventListener('click', e => this.onButton(e));
    $('.path', this.el).addEventListener('keydown', e => { if (e.key === 'Enter') this.load(e.target.value.trim()); });
    $('.filter', this.el).addEventListener('input', e => { this.filter = e.target.value.toLowerCase(); this.render(); });
    $('.hidden-toggle', this.el).addEventListener('change', e => {
      this.showHidden = e.target.checked; store.set(this.side + '.hidden', this.showHidden); this.render();
    });
    $('thead', this.el).addEventListener('click', e => {
      if (e.target.matches('input.all')) {
        const vis = this.visible();
        this.sel = e.target.checked ? new Set(vis.map(x => x.name)) : new Set();
        return this.render();
      }
      const th = e.target.closest('th[data-k]');
      if (!th) return;
      if (this.sortKey === th.dataset.k) this.sortDir = -this.sortDir;
      else { this.sortKey = th.dataset.k; this.sortDir = 1; }
      store.set(this.side + '.sortKey', this.sortKey); store.set(this.side + '.sortDir', this.sortDir);
      this.render();
    });

    this.tbody.addEventListener('click', e => this.onRowClick(e));
    this.tbody.addEventListener('dblclick', e => {
      const tr = e.target.closest('tr');
      if (!tr || e.target.matches('input') || Date.now() < (this.clickGuard || 0)) return;
      if (tr.dataset.up) return;  // already handled by the single click
      const ent = this.byName(tr.dataset.name);
      if (ent?.dir) return;
      else if (ent) { this.sel = new Set([ent.name]); this.render(); this.transfer(); }
    });
    this.list.addEventListener('contextmenu', e => this.onContext(e));
    this.list.addEventListener('keydown', e => this.onKey(e));

    // drag & drop
    this.tbody.addEventListener('dragstart', e => {
      const tr = e.target.closest('tr[data-name]');
      if (!tr) return e.preventDefault();
      if (!this.sel.has(tr.dataset.name)) { this.sel = new Set([tr.dataset.name]); this.render(); }
      e.dataTransfer.setData('application/x-filebridge', JSON.stringify({ side: this.side, paths: this.selectedPaths() }));
      e.dataTransfer.effectAllowed = 'copyMove';
    });
    this.list.addEventListener('dragover', e => {
      if (!e.dataTransfer.types.includes('application/x-filebridge')) return;
      e.preventDefault();
      $$('tr.drop', this.el).forEach(x => x.classList.remove('drop'));
      const tr = this.dropRow(e);
      if (tr) tr.classList.add('drop');
      this.list.classList.toggle('drop-target', !tr);
    });
    this.list.addEventListener('dragleave', e => {
      if (!this.list.contains(e.relatedTarget)) this.clearDrop();
    });
    this.list.addEventListener('drop', e => {
      e.preventDefault();
      const tr = this.dropRow(e);
      this.clearDrop();
      let data;
      try { data = JSON.parse(e.dataTransfer.getData('application/x-filebridge')); } catch { return; }
      let target = this.path;
      if (tr?.dataset.up) target = this.parentPath;
      else if (tr) target = this.byName(tr.dataset.name).path;
      if (data.side === this.side) {
        if (target === this.path) return;
        this.move(data.paths, target);
      } else {
        startTransfer(data.side === 'local' ? 'upload' : 'download', data.paths, target);
      }
    });
  }

  dropRow(e) {
    const tr = e.target.closest('tr');
    if (!tr) return null;
    if (tr.dataset.up) return tr;
    const ent = this.byName(tr.dataset.name);
    return ent?.dir && !this.sel.has(ent.name) ? tr : null;
  }
  clearDrop() {
    this.list.classList.remove('drop-target');
    $$('tr.drop', this.el).forEach(x => x.classList.remove('drop'));
  }

  byName(n) { return this.entries.find(e => e.name === n); }
  selected() { return this.entries.filter(e => this.sel.has(e.name)); }
  selectedPaths() { return this.selected().map(e => e.path); }

  async load(path, keepSelection = false) {
    if (this.remote && !S.status.connected) { this.entries = []; this.path = ''; return this.render(); }
    try {
      const r = await api('list', { side: this.side, path });
      const changed = r.path !== this.path;
      this.path = r.path;
      this.entries = r.entries;
      this.localParent = r.parent ?? null;
      if (changed) { this.filter = ''; $('.filter', this.el).value = ''; }
      if (changed || !keepSelection) this.sel = new Set();
      else this.sel = new Set([...this.sel].filter(n => this.byName(n)));
      if (!this.remote) store.set('localPath', this.path);
      this.render();
      if (S.highlight) this.other.render();
    } catch (e) {
      toast(e.message, 'error');
      $('.path', this.el).value = this.path;
    }
  }
  refresh() { return this.load(this.path, true); }

  visible() {
    let list = this.entries;
    if (!this.showHidden) list = list.filter(e => !e.hidden);
    if (this.filter) list = list.filter(e => e.name.toLowerCase().includes(this.filter));
    const k = this.sortKey, d = this.sortDir;
    const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
    const cmp = {
      name: byName,
      type: (a, b) => (a.ext || '').localeCompare(b.ext || '') || byName(a, b),
      size: (a, b) => (a.size || 0) - (b.size || 0) || byName(a, b),
      mtime: (a, b) => a.mtime - b.mtime || byName(a, b),
      perms: (a, b) => (a.mode ?? -1) - (b.mode ?? -1) || byName(a, b),
    }[k] || byName;
    return [...list].sort((a, b) => (b.dir - a.dir) || d * cmp(a, b));
  }

  render() {
    $('.path', this.el).value = this.path;
    $$('th[data-k]', this.el).forEach(th => {
      th.classList.toggle('sorted', th.dataset.k === this.sortKey);
      th.classList.toggle('desc', th.dataset.k === this.sortKey && this.sortDir < 0);
    });
    const empty = $('.empty', this.el);
    if (this.remote && !S.status.connected) {
      this.tbody.innerHTML = '';
      empty.hidden = false;
      empty.innerHTML = 'Not connected.<br>Choose a site at the top and click <b>Connect</b>.';
      this.renderFoot();
      return;
    }
    const vis = this.visible();
    const cols = 6;
    const om = S.highlight && this.canCompare() ? this.otherMap() : null;
    const diffCount = { new: 0, changed: 0 };
    let html = this.parentPath ? `<tr data-up="1"><td class="c-chk"></td><td class="c-name">${ICON.up}<span class="nm">..</span></td>${'<td></td>'.repeat(cols - 2)}</tr>` : '';
    for (const e of vis) {
      const s = this.sel.has(e.name);
      const d = om ? this.diffOf(e, om) : '';
      if (d) diffCount[d === 'new' ? 'new' : 'changed']++;
      html += `<tr data-name="${esc(e.name)}" class="${s ? 'sel' : ''} ${e.hidden ? 'hidden-file' : ''} ${d ? 'cmp-' + d : ''} ${e.dir ? 'is-dir' : ''}" draggable="true">
        <td class="c-chk"><input type="checkbox" ${s ? 'checked' : ''}></td>
        <td class="c-name" title="${esc(e.name)}">${e.dir ? ICON.dir : ICON.file}<span class="nm">${esc(e.name)}${e.link ? ' <span class="muted">↪</span>' : ''}</span></td>
        <td class="c-type">${esc(typeLabel(e))}</td>
        <td class="c-size num">${e.dir ? '' : fmtSize(e.size)}</td>
        <td class="c-date">${fmtDate(e.mtime)}</td>
        <td class="c-perm" title="${esc(e.perms)}">${modeText(e.mode)} <span class="oct">${modeOct(e.mode)}</span></td>
      </tr>`;
    }
    this.tbody.innerHTML = html;
    empty.hidden = vis.length > 0;
    empty.textContent = this.filter ? 'No matches' : 'Empty folder';
    const all = $('input.all', this.el);
    all.checked = vis.length > 0 && vis.every(x => this.sel.has(x.name));
    all.indeterminate = !all.checked && vis.some(x => this.sel.has(x.name));
    this.diffCount = om ? diffCount : null;
    this.renderFoot();
  }
  renderFoot() {
    const vis = this.remote && !S.status.connected ? [] : this.visible();
    const sel = this.selected();
    const files = vis.filter(e => !e.dir).length;
    $('.count', this.el).textContent = vis.length ? `${vis.length - files} folders, ${files} files` : '';
    const size = sel.reduce((n, e) => n + (e.size || 0), 0);
    $('.selinfo', this.el).textContent = sel.length ? `${sel.length} selected${size ? ' (' + fmtSize(size) + ')' : ''}` : '';
    const dc = this.diffCount;
    $('.diffinfo', this.el).innerHTML = dc && (dc.new || dc.changed)
      ? `<span class="cmp-legend new">${dc.new} not on ${this.remote ? 'local' : 'server'}</span><span class="cmp-legend changed">${dc.changed} changed</span>` : '';
  }

  openDir(path) {
    this.clickGuard = Date.now() + 500;  // ignore the 2nd click of a double-click in the new folder
    this.load(path);
  }

  onRowClick(e) {
    if (Date.now() < (this.clickGuard || 0)) return;
    if (e.target.closest('tr[data-up]')) return this.parentPath && this.openDir(this.parentPath);
    const tr = e.target.closest('tr[data-name]');
    if (!tr) return;
    const name = tr.dataset.name;
    const names = this.visible().map(x => x.name);
    const toggle = e.metaKey || e.ctrlKey || e.target.matches('input[type=checkbox]');
    const ent = this.byName(name);
    if (ent?.dir && !toggle && !e.shiftKey) return this.openDir(ent.path);  // one click opens a folder
    if (e.shiftKey && this.anchor && names.includes(this.anchor)) {
      const a = names.indexOf(this.anchor), b = names.indexOf(name);
      if (!toggle) this.sel = new Set();
      for (let i = Math.min(a, b); i <= Math.max(a, b); i++) this.sel.add(names[i]);
    } else if (toggle) {
      this.sel.has(name) ? this.sel.delete(name) : this.sel.add(name);
      this.anchor = name;
    } else {
      this.sel = new Set([name]);
      this.anchor = name;
    }
    this.render();
    this.list.focus({ preventScroll: true });
  }

  onKey(e) {
    if (e.target !== this.list) return;
    const vis = this.visible();
    const k = e.key;
    if ((e.metaKey || e.ctrlKey) && k === 'a') { e.preventDefault(); this.sel = new Set(vis.map(x => x.name)); this.render(); }
    else if (k === 'Escape') { this.sel = new Set(); this.render(); }
    else if (k === 'Delete' || k === 'Backspace') { e.preventDefault(); this.del(); }
    else if (k === 'F2') { e.preventDefault(); this.rename(); }
    else if ((e.metaKey || e.altKey) && k === 'ArrowUp') { e.preventDefault(); if (this.parentPath) this.load(this.parentPath); }
    else if (k === 'Enter') {
      const s = this.selected();
      if (s.length === 1 && s[0].dir) this.load(s[0].path);
    } else if (k === 'ArrowDown' || k === 'ArrowUp') {
      e.preventDefault();
      const names = vis.map(x => x.name);
      let i = names.indexOf(this.anchor);
      i = k === 'ArrowDown' ? Math.min(names.length - 1, i + 1) : Math.max(0, i - 1);
      if (!names[i]) return;
      if (e.shiftKey) this.sel.add(names[i]); else this.sel = new Set([names[i]]);
      this.anchor = names[i];
      this.render();
      $(`tr[data-name="${CSS.escape(names[i])}"]`, this.tbody)?.scrollIntoView({ block: 'nearest' });
    }
  }

  onButton(e) {
    const b = e.target.closest('button[data-a]');
    if (!b) return;
    const a = b.dataset.a;
    const r = b.getBoundingClientRect();
    ({
      up: () => this.parentPath && this.load(this.parentPath),
      refresh: () => this.refresh(),
      pick: async () => { const p = await pickLocal('folder', { start: this.path, prompt: 'Open folder' }); if (p) this.load(p); },
      bookmarks: () => bookmarksMenu(r.left, r.bottom + 4),
      transfer: () => this.transfer(),
      mkdir: () => this.mkdir(),
      rename: () => this.rename(),
      move: () => this.moveAsk(),
      delete: () => this.del(),
      chmod: () => this.chmod(),
      types: () => this.typesMenu(r.left, r.bottom + 4),
      permsel: () => this.permsMenu(r.left, r.bottom + 4),
      selnew: () => this.newMenu(r.left, r.bottom + 4),
    })[a]?.();
  }

  onContext(e) {
    e.preventDefault();
    setActive(this);
    const tr = e.target.closest('tr[data-name]');
    if (tr && !this.sel.has(tr.dataset.name)) { this.sel = new Set([tr.dataset.name]); this.render(); }
    const sel = this.selected();
    const n = sel.length;
    const conn = S.status.connected;
    const items = [
      n === 1 && sel[0].dir ? { label: 'Open', action: () => this.load(sel[0].path) } : null,
      { label: this.remote ? `Download${n > 1 ? ' ' + n + ' items' : ''}` : `Upload${n > 1 ? ' ' + n + ' items' : ''}`, hint: this.remote ? '←' : '→', disabled: !n || !conn, action: () => this.transfer() },
      n === 1 && !sel[0].dir && sel[0].ext === 'zip'
        ? { label: this.remote ? 'Extract here…' : 'Upload & extract…', disabled: !conn, action: () => openExtract(this) } : null,
      { sep: true },
      { label: 'Rename…', hint: 'F2', disabled: n !== 1, action: () => this.rename() },
      { label: 'Move to…', disabled: !n, action: () => this.moveAsk() },
      { label: 'Permissions…', disabled: !n || (this.remote && !conn), action: () => this.chmod() },
      { label: this.remote ? 'Delete…' : 'Move to Trash…', danger: true, disabled: !n, action: () => this.del() },
      { sep: true },
      { label: 'New folder…', action: () => this.mkdir() },
      { label: 'Refresh', action: () => this.refresh() },
      { label: 'Copy path', disabled: !n, action: () => copyText(this.selectedPaths().join('\n')).then(ok => toast(ok ? 'Path copied' : 'Could not copy', ok ? '' : 'error')) },
      !this.remote ? { label: `Show in ${S.platform?.file_manager || 'Finder'}`, action: () => api('reveal', { path: n === 1 ? sel[0].path : this.path }) } : null,
    ];
    const plugs = S.plugins.filter(p => p.side === 'any' || p.side === this.side);
    if (plugs.length) {
      items.push({ sep: true }, { header: 'Plugins' });
      for (const p of plugs) items.push({ label: p.label, disabled: p.needs_selection && !n, action: () => runPlugin(p, this) });
    }
    showMenu(e.clientX, e.clientY, items);
  }

  // --- compare with the folder that is open on the other side ---
  canCompare() { return S.status.connected && !!this.other.path && !!this.path; }
  otherMap() { return new Map(this.other.entries.map(x => [x.name, x])); }
  /** '' (same), 'new' (not on the other side), 'changed' (different size/type), 'newer' (same size, newer here) */
  diffOf(e, om) {
    const o = om.get(e.name);
    if (!o) return 'new';
    if (e.dir || o.dir) return e.dir === o.dir ? '' : 'changed';
    if (e.size !== o.size) return 'changed';
    if (e.mtime > o.mtime + 2) return 'newer';
    return '';
  }

  newMenu(x, y) {
    if (!this.canCompare()) return toast('Connect and open the matching folder on the other side first');
    const om = this.otherMap();
    const vis = this.visible();
    const by = kinds => vis.filter(e => kinds.includes(this.diffOf(e, om))).map(e => e.name);
    const there = this.remote ? 'local' : 'the server';
    const pick = (names, what) => () => {
      this.sel = new Set(names);
      this.render();
      toast(names.length ? `Selected ${names.length} item(s) ${what} – click ${this.remote ? '← Download' : 'Upload →'}` : 'Nothing to select – everything is already there', names.length ? 'ok' : '');
    };
    const missing = by(['new']), changed = by(['changed', 'newer']);
    showMenu(x, y, [
      { header: `Compared with ${this.other.path}` },
      { label: `Not on ${there}`, hint: String(missing.length), action: pick(missing, `not on ${there}`) },
      { label: `Not on ${there} + changed here`, hint: String(missing.length + changed.length), action: pick([...missing, ...changed], `new or changed`) },
      { label: 'Changed here only', hint: String(changed.length), action: pick(changed, 'changed here') },
      { sep: true },
      { label: `${S.highlight ? '✓ ' : ''}Highlight differences`, action: () => {
        S.highlight = !S.highlight; store.set('highlight', S.highlight); PL.render(); PR.render();
      } },
      { header: 'Folders that exist on both sides are compared by name only.' },
      { header: 'Tip: “Skip if exists” also skips files inside them.' },
    ]);
  }

  permsMenu(x, y) {
    const vis = this.visible().filter(e => e.mode != null);
    const groups = new Map();
    for (const e of vis) { if (!groups.has(e.mode)) groups.set(e.mode, []); groups.get(e.mode).push(e); }
    if (!groups.size) return toast('Nothing to select');
    const items = [{ header: 'Click to add / remove from selection' }];
    for (const [m, list] of [...groups].sort((a, b) => b[1].length - a[1].length || a[0] - b[0])) {
      const names = list.map(e => e.name);
      const allSel = names.every(n => this.sel.has(n));
      const d = list.filter(e => e.dir).length, f = list.length - d;
      items.push({
        label: `${allSel ? '✓ ' : ''}${modeOct(m)}  ${modeText(m)}`,
        hint: [d && `${d} folder${d > 1 ? 's' : ''}`, f && `${f} file${f > 1 ? 's' : ''}`].filter(Boolean).join(', '),
        action: () => { names.forEach(n => allSel ? this.sel.delete(n) : this.sel.add(n)); this.render(); },
      });
    }
    items.push({ sep: true }, { label: 'Clear selection', action: () => { this.sel = new Set(); this.render(); } });
    showMenu(x, y, items);
  }

  typesMenu(x, y) {
    const vis = this.visible();
    const groups = {};
    for (const e of vis) {
      const k = e.dir ? '(folders)' : (e.ext ? '.' + e.ext : '(no extension)');
      (groups[k] ||= []).push(e.name);
    }
    const keys = Object.keys(groups).sort((a, b) => groups[b].length - groups[a].length || a.localeCompare(b));
    if (!keys.length) return toast('Nothing to select');
    const items = [{ header: 'Click to add / remove from selection' }];
    for (const k of keys) {
      const names = groups[k];
      const allSel = names.every(n => this.sel.has(n));
      items.push({
        label: `${allSel ? '✓ ' : ''}${k}`, hint: String(names.length),
        action: () => { names.forEach(n => allSel ? this.sel.delete(n) : this.sel.add(n)); this.render(); },
      });
    }
    items.push({ sep: true }, { label: 'Select all', action: () => { this.sel = new Set(vis.map(x => x.name)); this.render(); } },
      { label: 'Invert selection', action: () => { this.sel = new Set(vis.filter(x => !this.sel.has(x.name)).map(x => x.name)); this.render(); } },
      { label: 'Clear selection', action: () => { this.sel = new Set(); this.render(); } });
    showMenu(x, y, items);
  }

  needSel(min = 1) {
    if (this.sel.size < min) { toast('Select one or more items first'); return false; }
    return true;
  }

  transfer() {
    if (!this.needSel()) return;
    if (!S.status.connected) return toast('Connect to a server first', 'error');
    startTransfer(this.remote ? 'download' : 'upload', this.selectedPaths(), this.other.path);
  }

  async mkdir() {
    const name = await askText('New folder', `Name of the new folder in ${this.path}`);
    if (!name) return;
    try { await api('mkdir', { side: this.side, dir: this.path, name }); await this.refresh(); }
    catch (e) { toast(e.message, 'error'); }
  }

  async rename() {
    const s = this.selected();
    if (s.length !== 1) return toast('Select exactly one item to rename');
    const name = await askText('Rename', 'New name', s[0].name);
    if (!name || name === s[0].name) return;
    try { await api('rename', { side: this.side, path: s[0].path, name }); this.sel = new Set([name]); await this.refresh(); }
    catch (e) { toast(e.message, 'error'); }
  }

  async moveAsk() {
    if (!this.needSel()) return;
    const dest = await askText('Move', `Move ${this.sel.size} item(s) to folder:`, this.path);
    if (!dest || dest === this.path) return;
    this.move(this.selectedPaths(), dest);
  }
  async move(paths, dest) {
    try {
      await api('move', { side: this.side, paths, dest });
      toast(`Moved ${paths.length} item(s)`, 'ok');
      await this.refresh();
    } catch (e) { toast(e.message, 'error'); }
  }

  async del() {
    if (!this.needSel()) return;
    const s = this.selected();
    const list = s.slice(0, 8).map(e => '• ' + esc(e.name) + (e.dir ? '/' : '')).join('<br>') + (s.length > 8 ? `<br>… and ${s.length - 8} more` : '');
    const ok = this.remote
      ? await confirmBox('Delete on server', `Permanently delete ${s.length} item(s) from the server? Folders are deleted with everything in them. This cannot be undone.<br><br>${list}`, 'Delete', true)
      : await confirmBox('Move to Trash', `Move ${s.length} item(s) to the Trash?<br><br>${list}`, 'Move to Trash', true);
    if (!ok) return;
    try { await api('delete', { side: this.side, paths: this.selectedPaths() }); toast(`Deleted ${s.length} item(s)`, 'ok'); await this.refresh(); }
    catch (e) { toast(e.message, 'error'); this.refresh(); }
  }

  chmod() {
    if (this.remote && !S.status.connected) return toast('Connect to a server first', 'error');
    if (!this.needSel()) return;
    openChmod(this);
  }
}

function setActive(p) {
  S.active = p;
  PL.el.classList.toggle('active', p === PL);
  PR.el.classList.toggle('active', p === PR);
}

/* ---------------------------------------------------------------- permissions (chmod) */
const PERM_GROUPS = [
  ['Owner permissions', [['Read', 0o400], ['Write', 0o200], ['Execute', 0o100]]],
  ['Group permissions', [['Read', 0o40], ['Write', 0o20], ['Execute', 0o10]]],
  ['Public permissions', [['Read', 0o4], ['Write', 0o2], ['Execute', 0o1]]],
  ['Special permissions', [['Set-user-ID', 0o4000], ['Set-group-ID', 0o2000], ['Sticky bit', 0o1000]]],
];
const PERM_BITS = PERM_GROUPS.flatMap(g => g[1].map(b => b[1]));
const PERM_DIGITS = [[0o4000, 0o2000, 0o1000], [0o400, 0o200, 0o100], [0o40, 0o20, 0o10], [0o4, 0o2, 0o1]];

/** state: {bit: 1 | 0 | null}; null = keep each item's own value ("x" in the number). */
function permStateText(st) {
  return PERM_DIGITS.map(ds => ds.some(b => st[b] == null) ? 'x' : ds.reduce((n, b, i) => n + (st[b] ? [4, 2, 1][i] : 0), 0)).join('');
}
/** Parse "755", "0644", "0x55" or "u+x,go-w", "a=rx" into a new state; null if invalid. */
function parsePermText(text, st) {
  const t = text.trim().toLowerCase();
  if (!t) return null;
  const out = { ...st };
  if (/^[0-7x]{1,4}$/.test(t)) {
    const d = t.padStart(4, '0');
    PERM_DIGITS.forEach((ds, i) => ds.forEach((b, j) => { out[b] = d[i] === 'x' ? null : ((+d[i] >> (2 - j)) & 1); }));
    return out;
  }
  const CLS = { u: [0o400, 0o200, 0o100, 0o4000], g: [0o40, 0o20, 0o10, 0o2000], o: [0o4, 0o2, 0o1, 0o1000] };
  for (const part of t.split(',')) {
    const m = part.trim().match(/^([ugoa]*)([+\-=])([rwxst]*)$/);
    if (!m) return null;
    for (const c of new Set((m[1] || 'a').replace(/a/g, 'ugo'))) {
      const [r, w, x, sp] = CLS[c];
      const bits = { r, w, x, s: c === 'o' ? null : sp, t: c === 'o' ? sp : null };
      if (m[2] === '=') [r, w, x, sp].forEach(b => { out[b] = 0; });
      for (const ch of m[3]) if (bits[ch] != null) out[bits[ch]] = m[2] === '-' ? 0 : 1;
    }
  }
  return out;
}

async function openChmod(pane) {
  const sel = pane.selected();
  const known = sel.filter(e => e.mode != null);
  const initial = {};
  for (const b of PERM_BITS) {
    const vals = new Set(known.map(e => (e.mode & b) ? 1 : 0));
    initial[b] = vals.size === 1 ? [...vals][0] : null;
  }
  const mixedBits = new Set(PERM_BITS.filter(b => initial[b] == null));
  let state = { ...initial };
  const modes = new Set(known.map(e => e.mode));
  const hasDir = sel.some(e => e.dir);
  const what = sel.length === 1 ? `the ${sel[0].dir ? 'directory' : 'file'} "${esc(sel[0].name)}"` : `the ${sel.length} selected items`;
  const body = `
    <p style="margin-top:0">Please select the new attributes for ${what}.</p>
    ${PERM_GROUPS.map(([title, bits]) => `<div class="perm-title">${title}</div>
      <div class="perm-box">${bits.map(([l, b]) => `<label class="check"><input type="checkbox" data-bit="${b}"> ${l}</label>`).join('')}</div>`).join('')}
    <div class="perm-chmod"><label for="chmodText">Chmod:</label><input id="chmodText" class="mono" spellcheck="false" autocomplete="off"></div>
    <p class="muted sm-note">Enter the new mode in octal (e.g. 755 or 0644) or as a textual change (e.g. u+x,go-w).
      ${mixedBits.size ? 'The selected items differ: a mixed box (–) or an x in the number means “leave as it is on each item”.' : ''}</p>
    ${hasDir ? `<label class="check"><input type="checkbox" id="chmodRec"> Recurse into subdirectories</label>
      <div class="perm-indent">
        <label class="check"><input type="radio" name="applyTo" value="all" checked disabled> Apply to all files and directories</label>
        <label class="check"><input type="radio" name="applyTo" value="files" disabled> Apply to files only</label>
        <label class="check"><input type="radio" name="applyTo" value="dirs" disabled> Apply to directories only</label>
      </div>` : ''}
    <div class="perm-sep"></div>
    <label class="check"><input type="checkbox" id="chmodOnly"> Only change items that currently have permissions</label>
    <div class="perm-indent"><input id="chmodOnlyVal" class="mono" placeholder="e.g. 0777" style="width:130px" value="${modes.size === 1 ? modeOct([...modes][0]) : ''}"></div>`;

  const { value, el } = await modal({
    title: 'Change file attributes', body, size: 'perm-size',
    buttons: [{ label: 'Cancel', value: null }, { label: 'OK', value: 'ok', primary: true }],
    onOpen(m) {
      const text = $('#chmodText', m);
      const boxes = $$('[data-bit]', m);
      const paint = () => boxes.forEach(cb => {
        const v = state[+cb.dataset.bit];
        cb.checked = v === 1;
        cb.indeterminate = v == null;
      });
      paint();
      text.value = permStateText(state);
      boxes.forEach(cb => cb.addEventListener('click', () => {
        const b = +cb.dataset.bit;
        const v = state[b];
        // 0 → 1 → (mixed, only if the items differed) → 0
        state[b] = v === 0 ? 1 : v === 1 ? (mixedBits.has(b) ? null : 0) : 0;
        paint();
        text.value = permStateText(state);
        text.classList.remove('bad');
      }));
      text.addEventListener('input', () => {
        const next = parsePermText(text.value, state);
        text.classList.toggle('bad', !next);
        if (next) { state = next; paint(); }
      });
      const rec = $('#chmodRec', m);
      if (rec) rec.addEventListener('change', () => $$('[name=applyTo]', m).forEach(r => { r.disabled = !rec.checked; }));
      const onlyVal = $('#chmodOnlyVal', m);
      onlyVal.addEventListener('input', () => { $('#chmodOnly', m).checked = !!onlyVal.value.trim(); });
      setTimeout(() => { text.focus(); text.select(); }, 0);
    },
  });
  if (!value) return;
  const set = PERM_BITS.filter(b => state[b] === 1).reduce((a, b) => a | b, 0);
  const clear = PERM_BITS.filter(b => state[b] === 0).reduce((a, b) => a | b, 0);
  if ($('#chmodText', el).classList.contains('bad')) return toast('The chmod value is not valid', 'error');
  const recursive = !!$('#chmodRec', el)?.checked;
  const onlyIf = $('#chmodOnly', el).checked ? $('#chmodOnlyVal', el).value.trim() : '';
  if ($('#chmodOnly', el).checked && !onlyIf) return toast('Fill in the permissions to match, e.g. 0777', 'error');
  try {
    const r = await api('chmod', {
      side: pane.side, paths: pane.selectedPaths(), set, clear, recursive,
      apply_to: recursive ? ($('[name=applyTo]:checked', el)?.value || 'all') : 'all', only_if: onlyIf,
    });
    watchJob(r.job_id, job => { if (job.status === 'done') toast(job.result?.message || 'Permissions changed', 'ok'); });
  } catch (e) { toast(e.message, 'error'); }
}

/* ---------------------------------------------------------------- extract zip */
async function openExtract(pane) {
  if (!S.status.connected) return toast('Connect to a server first', 'error');
  const sel = pane.selected();
  if (sel.length !== 1 || sel[0].dir || sel[0].ext !== 'zip') return toast('Select one .zip file');
  const z = sel[0];
  const fromLocal = !pane.remote;
  const site = S.sites.find(x => x.id === S.status.site_id) || {};
  const dDir = (site.upload_perms && site.upload_dir_mode) || '0755';
  const dFile = (site.upload_perms && site.upload_file_mode) || '0644';
  const dest = fromLocal ? PR.path : pane.path;
  const base = z.name.replace(/\.zip$/i, '');
  const ftp = S.status.protocol === 'FTP';
  const body = `
    <p style="margin-top:0">${fromLocal ? `Upload <b>${esc(z.name)}</b> (${fmtSize(z.size)}) and extract it on the server.` : `Extract <b>${esc(z.name)}</b> on the server.`}</p>
    <label class="field">Extract to (server folder)<span class="with-btn"><input id="xDest" value="${esc(dest)}"><button type="button" data-current="remote">Use current</button></span></label>
    <label class="check"><input type="radio" name="xInto" value="here" checked> Directly into this folder</label>
    <label class="check"><input type="radio" name="xInto" value="folder"> Into a new folder “${esc(base)}”</label>
    <label class="check"><input type="checkbox" id="xStrip"> Leave out the zip's top folder (extract only what is inside it)</label>
    <div id="xPreview" class="info-box"><span class="muted">Reading the zip…</span></div>
    <div class="perm-sep"></div>
    <div class="row"><label class="field">Files that already exist on the server
      <select id="xPolicy"><option value="overwrite">Overwrite them</option><option value="skip_exists">Keep them (only add new files)</option></select></label></div>
    <label class="check"><input type="checkbox" id="xPerms" checked> Set permissions on the extracted files</label>
    <div class="sm-upperm">
      <label>Folders <input id="xDirMode" class="mono" value="${esc(dDir)}"></label>
      <label>Files <input id="xFileMode" class="mono" value="${esc(dFile)}"></label>
    </div>
    ${fromLocal ? '' : '<label class="check"><input type="checkbox" id="xDel"> Delete the zip from the server afterwards</label>'}
    <div class="perm-sep"></div>
    <div class="row"><label class="field">Unpack
      <select id="xMethod">
        <option value="auto">Automatic</option>
        <option value="server" ${ftp ? 'disabled' : ''}>On the server (fast, needs SSH + unzip)</option>
        <option value="local">On this computer, then upload the files</option>
      </select></label></div>
    <p class="muted sm-note">${ftp
      ? 'This is an FTP connection: the zip is unpacked on this computer and the files are uploaded with the permissions above.'
      : 'Automatic unpacks on the server when it allows SSH commands, otherwise on this computer.'}</p>`;
  const { value, el } = await modal({
    title: fromLocal ? 'Upload & extract' : 'Extract zip', body, size: 'mid',
    buttons: [{ label: 'Cancel', value: null }, { label: fromLocal ? 'Upload & extract' : 'Extract', value: 'ok', primary: true }],
    onOpen(m) {
      ['#xDirMode', '#xFileMode'].forEach(id => $(id, m).addEventListener('input', () => { $('#xPerms', m).checked = true; }));
      // Preview: show exactly where the files will end up, and warn about a likely mistake
      let info = null, destNames = null, destFor = null;
      const box = $('#xPreview', m);
      const render = async () => {
        if (!info) return;
        const destVal = $('#xDest', m).value.trim().replace(/\/+$/, '') || '/';
        const into = $('input[name=xInto]:checked', m).value === 'folder';
        const strip = $('#xStrip', m).checked;
        const target = into ? `${destVal === '/' ? '' : destVal}/${base}` : destVal;
        const top = info.top_folder;
        const map = p => (strip && top && p.startsWith(top + '/') ? p.slice(top.length + 1) : p);
        const rows = info.sample.slice(0, 3).map(p => `<div class="mono">${esc(p)} <span class="muted">→</span> ${esc((target === '/' ? '' : target) + '/' + map(p))}</div>`).join('');
        let warn = '';
        if (destFor !== destVal) {
          destFor = destVal; destNames = null;
          try { destNames = new Set((await api('list', { side: 'remote', path: destVal })).entries.map(e => e.name)); } catch { destNames = null; }
        }
        if (strip && top && !into && destNames?.has(top)) {
          warn = `<div class="err" style="margin-top:8px">⚠ This folder already contains “${esc(top)}/”. With “Leave out the zip's top folder” on, the files do <b>not</b> go into “${esc(top)}/” and the existing files there are <b>not</b> replaced. Untick it to update “${esc(top)}/”.</div>`;
        }
        box.innerHTML = `<b>Result</b> (${info.files} files${top ? `, top folder “${esc(top)}/”` : ''}):${rows}${info.files > 3 ? '<div class="muted">…</div>' : ''}${warn}`;
      };
      api('zip_info', { side: pane.side, zip: z.path }).then(r => {
        info = r.info;
        if (!info) { box.innerHTML = '<span class="muted">The zip is too large to preview; it will be extracted as shown by the options above.</span>'; return; }
        if (!info.top_folder) $('#xStrip', m).closest('label').hidden = true;
        render();
      }).catch(e => { box.innerHTML = `<span class="muted">Could not read the zip: ${esc(e.message)}</span>`; });
      ['#xDest', '#xStrip'].forEach(id => $(id, m).addEventListener('input', render));
      $('#xStrip', m).addEventListener('change', render);
      $$('input[name=xInto]', m).forEach(r => r.addEventListener('change', render));
      $('#xDest', m).addEventListener('change', render);
    },
  });
  if (!value) return;
  const destVal = $('#xDest', el).value.trim();
  const into = $('input[name=xInto]:checked', el).value === 'folder';
  try {
    const r = await api('extract', {
      side: pane.side, zip: z.path, dest: destVal, into_folder: into, strip: $('#xStrip', el).checked,
      policy: $('#xPolicy', el).value,
      perms: $('#xPerms', el).checked ? { dirs: $('#xDirMode', el).value, files: $('#xFileMode', el).value } : null,
      delete_zip: !!$('#xDel', el)?.checked, method: $('#xMethod', el).value,
    });
    watchJob(r.job_id, job => {
      if (job.status !== 'done') return;
      toast(job.result?.message || 'Extracted', 'ok');
      if (PR.path === destVal && into) PR.refresh();
    });
  } catch (e) { toast(e.message, 'error'); }
}

/* ---------------------------------------------------------------- transfers & jobs */
async function startTransfer(direction, paths, dest, onDone) {
  if (!S.status.connected) return toast('Connect to a server first', 'error');
  if (!dest) return toast('No destination folder', 'error');
  try {
    const r = await api('transfer', { direction, paths, dest, policy: $('#policy').value });
    watchJob(r.job_id, onDone || (job => { if (job.status === 'done' && job.result?.message) toast(job.result.message, 'ok'); }));
  } catch (e) { toast(e.message, 'error'); }
}

function watchJob(id, fn) {
  S.callbacks[id] = fn || (() => {});
  kickPoll();
}

let pollTimer = null;
function kickPoll() { clearTimeout(pollTimer); pollTimer = setTimeout(poll, 150); }
async function poll() {
  let active = false;
  try {
    const r = await api('jobs');
    active = r.jobs.some(j => j.status === 'running' || j.status === 'queued');
    renderJobs(r.jobs);
    renderLog(r.log);
    applyStatus(r.status);
    for (const j of r.jobs) {
      if (S.callbacks[j.id] && ['done', 'error', 'cancelled'].includes(j.status)) {
        const cb = S.callbacks[j.id];
        delete S.callbacks[j.id];
        if (j.refresh.includes('local')) PL.refresh();
        if (j.refresh.includes('remote') && S.status.connected) PR.refresh();
        if (j.status === 'error') toast(j.error, 'error');
        cb(j);
      }
    }
  } catch { /* server stopped? keep trying */ }
  pollTimer = setTimeout(poll, active || Object.keys(S.callbacks).length ? 500 : 2000);
}

function renderJobs(jobs) {
  const active = jobs.filter(j => j.status === 'running' || j.status === 'queued').length;
  const badge = $('#queueCount');
  badge.hidden = !active;
  badge.textContent = active;
  const q = $('#queue');
  if (!jobs.length) { q.innerHTML = '<div class="empty">No transfers yet. Select files and click Upload/Download, or drag them to the other side.</div>'; return; }
  q.innerHTML = jobs.map(j => {
    const pct = j.total ? Math.min(100, Math.round(j.done / j.total * 100)) : (j.status === 'done' ? 100 : 0);
    const items = j.unit === 'items';
    const fmt = n => items ? `${n}` : fmtSize(n);
    const sizeTxt = j.total ? `${fmt(j.done)} / ${fmt(j.total)}${items ? ' items' : ''}` : (j.done ? fmt(j.done) : '');
    const speed = j.status === 'running' && j.speed && !items ? ` · ${fmtSize(j.speed)}/s` : '';
    const label = { queued: 'Waiting', running: j.current || 'Working…', done: 'Done', error: 'Failed', cancelled: 'Cancelled' }[j.status];
    return `<div class="job ${j.status}">
      <span class="dot"></span>
      <div style="min-width:0"><div class="title" title="${esc(j.title)}">${esc(j.title)}</div>
        ${j.error ? `<div class="err">${esc(j.error)}</div>` : `<div class="sub">${esc(label)}</div>`}</div>
      <div class="bar"><i style="width:${pct}%"></i></div>
      <div class="sub">${sizeTxt}${speed}</div>
      <div>${['queued', 'running'].includes(j.status) ? `<button class="small" data-cancel="${j.id}">Cancel</button>` : ''}</div>
    </div>`;
  }).join('');
}
$('#queue').addEventListener('click', e => {
  const id = e.target.dataset.cancel;
  if (id) api('job_cancel', { id }).then(kickPoll);
});
$('#btnClearJobs').onclick = () => api('jobs_clear').then(kickPoll);

let lastLogLen = -1;
function renderLog(log) {
  const key = log.length + (log.at(-1)?.msg || '');
  if (key === lastLogLen) return;
  lastLogLen = key;
  const el = $('#log');
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  el.innerHTML = log.map(l => `<div class="l-${l.level}"><span class="t">${l.t}</span>${esc(l.msg)}</div>`).join('');
  if (atBottom) el.scrollTop = el.scrollHeight;
}
$$('.tab').forEach(t => t.onclick = () => {
  $$('.tab').forEach(x => x.classList.toggle('active', x === t));
  $('#queue').hidden = t.dataset.tab !== 'queue';
  $('#log').hidden = t.dataset.tab !== 'log';
  if (t.dataset.tab === 'log') $('#log').scrollTop = 1e9;
});
$('#policy').value = store.get('policy', 'skip_exists');
S.highlight = store.get('highlight', false);
$('#policy').onchange = e => store.set('policy', e.target.value);

/* ---------------------------------------------------------------- connection */
function applyStatus(st) {
  const was = S.status.connected;
  S.status = st;
  const el = $('#connStatus');
  el.className = 'status' + (st.connected ? ' on' : '');
  el.textContent = st.connected ? st.label : 'Not connected';
  $('#btnConnect').hidden = st.connected;
  $('#btnDisconnect').hidden = !st.connected;
  document.body.dataset.siteColor = st.connected ? (st.color || '') : '';
  if (was && !st.connected) { PR.entries = []; PR.render(); }
}

function renderSites(selectId) {
  const sel = $('#siteSelect');
  const cur = selectId || sel.value || store.get('site', '');
  const opt = s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`;
  const groups = {};
  for (const s of S.sites) (groups[s.folder || ''] ||= []).push(s);
  sel.innerHTML = !S.sites.length ? '<option value="">(no sites yet)</option>'
    : (groups[''] || []).map(opt).join('') + Object.keys(groups).filter(Boolean).sort((a, b) => a.localeCompare(b))
      .map(f => `<optgroup label="${esc(f)}">${groups[f].map(opt).join('')}</optgroup>`).join('');
  if (S.sites.some(s => s.id === cur)) sel.value = cur;
}
$('#siteSelect').onchange = e => store.set('site', e.target.value);

async function connect(extra = {}) {
  const site = currentSite();
  if (!site) return openSiteManager();
  const el = $('#connStatus');
  el.className = 'status busy';
  el.textContent = `Connecting to ${site.host}…`;
  $('#btnConnect').disabled = true;
  try {
    const r = await api('connect', { site_id: site.id, ...extra });
    S.sites = r.sites;
    applyStatus(r.status);
    await PR.load(r.remote_path);
    if (site.local_dir) PL.load(site.local_dir);
    toast(`Connected to ${site.host}`, 'ok');
  } catch (e) {
    applyStatus({ connected: false });
    if (e.message.startsWith('NEED_PASSWORD')) {
      const failed = e.message.includes(':');
      const canSave = site.auth !== 'ask';
      const { value, el: m } = await modal({
        title: `Password for ${site.username}@${site.host}`,
        body: `${failed ? '<div class="info-box err">The server rejected the password. Check it and type it again.</div>' : ''}
               <label class="field">Password<input id="pw" type="password" autocomplete="off"></label>
               ${canSave ? `<label class="check"><input type="checkbox" id="pwSave" checked> Remember in ${esc(S.platform?.keychain || 'the system keychain')}</label>` : ''}`,
        buttons: [{ label: 'Cancel', value: null }, { label: 'Connect', value: 'ok', primary: true }],
      });
      if (value && $('#pw', m).value) return connect({ password: $('#pw', m).value, save: canSave && $('#pwSave', m).checked });
    } else {
      modal({ title: 'Connection failed', body: `<p>${esc(e.message)}</p>`, buttons: [{ label: 'OK', value: null, primary: true }] });
    }
  } finally {
    $('#btnConnect').disabled = false;
  }
}
$('#btnConnect').onclick = () => connect();
$('#btnDisconnect').onclick = async () => { applyStatus((await api('disconnect')).status); };

/* ---------------------------------------------------------------- native pickers */
/** Opens the native file/folder dialog (via the local server). Returns a path, or null if cancelled. */
async function pickLocal(kind, opts = {}) {
  try {
    const r = await api('pick', { kind, ...opts });
    return r.path || null;
  } catch (e) { toast(e.message, 'error'); return null; }
}
// "Browse…" buttons next to local path fields, and "Use current" next to server path fields
document.addEventListener('click', async e => {
  const b = e.target.closest('button[data-pick], button[data-current]');
  if (!b) return;
  e.preventDefault();
  const input = b.parentElement.querySelector('input');
  if (b.dataset.current) {
    if (!S.status.connected || !PR.path) return toast('Connect and open a folder in the server pane first');
    input.value = PR.path;
  } else {
    const cur = input.value.trim();
    const p = await pickLocal(b.dataset.pick, {
      start: cur || b.dataset.start || PL.path,
      types: b.dataset.types ? b.dataset.types.split(',') : [],
      invisibles: !!b.dataset.invisibles,
    });
    if (!p) return;
    input.value = p;
  }
  input.dispatchEvent(new Event('change', { bubbles: true }));
});

/* ---------------------------------------------------------------- site manager (FileZilla style) */
const PROTO_LABEL = { sftp: 'SFTP - SSH File Transfer Protocol', ftp: 'FTP - File Transfer Protocol' };
const ENC_LABEL = {
  auto: 'Use explicit FTP over TLS if available', explicit: 'Require explicit FTP over TLS',
  implicit: 'Require implicit FTP over TLS', plain: 'Only use plain FTP (insecure)',
};
const LOGON_LABEL = { password: 'Normal', ask: 'Ask for password', anonymous: 'Anonymous', key: 'Key file', agent: 'SSH agent / keys in ~/.ssh' };
const LOGONS = { sftp: ['password', 'ask', 'key', 'agent'], ftp: ['password', 'ask', 'anonymous'] };
const COLOR_LABEL = { '': 'None', red: 'Red', green: 'Green', blue: 'Blue', yellow: 'Yellow', cyan: 'Cyan', magenta: 'Magenta' };
const defaultPort = s => s.protocol === 'ftp' ? (s.encryption === 'implicit' ? 990 : 21) : 22;
const SERVER_ICON = '<svg class="ico sm-srv" viewBox="0 0 16 16"><rect x="3" y="1.5" width="10" height="13" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M5.5 5h5M5.5 7.5h5" stroke="currentColor" stroke-width="1.2"/><circle cx="8" cy="11.3" r="1" fill="currentColor"/></svg>';

function openSiteManager(focusId) {
  const work = structuredClone(S.sites);
  let folders = [...new Set([...(S.folders || []), ...work.map(s => s.folder).filter(Boolean)])];
  const deleted = [];
  const secrets = {};   // site id -> {password, passphrase} typed in this session
  let sel = null;       // {type: 'site', id} | {type: 'folder', name} | {type: 'root'}
  let tab = 'general';
  let tempN = 0;
  let el;
  const siteById = id => work.find(s => s.id === id);
  const E = n => $('#smForm', el).elements[n];
  const byName = (a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' });
  const opt = (map, keys) => (keys || Object.keys(map)).map(k => `<option value="${k}">${esc(map[k])}</option>`).join('');
  const allFolders = () => [...new Set([...folders, ...work.map(s => s.folder).filter(Boolean)])].sort((a, b) => a.localeCompare(b));

  const body = `<div class="sm">
    <div class="sm-left">
      <div class="sm-label">Select entry:</div>
      <div class="sm-tree" id="smTree"></div>
      <div class="sm-btns">
        <button type="button" data-sm="newsite">New site</button>
        <button type="button" data-sm="newfolder">New folder</button>
        <button type="button" data-sm="rename">Rename</button>
        <button type="button" data-sm="duplicate">Duplicate</button>
        <button type="button" data-sm="delete">Delete</button>
      </div>
    </div>
    <div class="sm-right">
      <div class="sm-tabs">
        <button type="button" class="sm-tab" data-tab="general">General</button>
        <button type="button" class="sm-tab" data-tab="advanced">Advanced</button>
        <button type="button" class="sm-tab" data-tab="transfer">Transfer Settings</button>
        <button type="button" class="sm-tab" data-tab="charset">Charset</button>
      </div>
      <form id="smForm" autocomplete="off" class="sm-form" onsubmit="return false">
        <div class="sm-empty muted">Select a site on the left, or click <b>New site</b>.</div>
        <div class="sm-page" data-page="general">
          <label>Protocol:</label><select name="protocol">${opt(PROTO_LABEL)}</select>
          <label>Host:</label><div class="sm-host"><input name="host" placeholder="example.com" spellcheck="false"><label>Port:</label><input name="port" class="sm-port"></div>
          <label data-proto="ftp">Encryption:</label><select name="encryption" data-proto="ftp">${opt(ENC_LABEL)}</select>
          <div data-proto="ftp" data-enc="plain"></div><div class="sm-warn" data-proto="ftp" data-enc="plain">Plain FTP sends your password and files unencrypted over the internet.</div>
          <div class="sm-sep"></div>
          <label>Logon Type:</label><select name="auth"></select>
          <label data-auth="password ask key agent">User:</label><input name="username" data-auth="password ask key agent" spellcheck="false">
          <label data-auth="password">Password:</label><input name="password" type="password" autocomplete="new-password" data-auth="password" data-noenter="1">
          <label data-auth="key">Key file:</label><div class="with-btn" data-auth="key"><input name="key_path" placeholder="~/.ssh/id_ed25519"><button type="button" data-pick="file" data-start="~/.ssh" data-invisibles="1">Browse…</button></div>
          <label data-auth="key agent">Passphrase:</label><input name="passphrase" type="password" autocomplete="new-password" data-auth="key agent" placeholder="only if your key has one">
          <div class="sm-sep"></div>
          <label>Background color:</label><div><select name="color" class="sm-color">${opt(COLOR_LABEL)}</select></div>
          <label class="sm-top">Comments:</label><textarea name="comments" rows="4"></textarea>
        </div>
        <div class="sm-page" data-page="advanced">
          <label>Default local directory:</label><div class="with-btn"><input name="local_dir" placeholder="~/Projects/site"><button type="button" data-pick="folder">Browse…</button></div>
          <label>Default remote directory:</label><div class="with-btn"><input name="remote_dir" placeholder="/public_html"><button type="button" data-current="remote">Use current</button></div>
          <div></div><p class="muted sm-note">These folders open automatically when you connect to this site.</p>
        </div>
        <div class="sm-page" data-page="transfer">
          <div class="sm-wide">
            <div class="sm-group">Permissions after upload</div>
            <label class="check"><input type="checkbox" name="upload_perms"> Give everything I upload to this site fixed permissions</label>
            <div class="sm-upperm">
              <label>Folders <input name="upload_dir_mode" class="mono" placeholder="0755"></label>
              <label>Files <input name="upload_file_mode" class="mono" placeholder="0644"></label>
            </div>
            <p class="muted sm-note">Applies to uploads, drag &amp; drop, sync, deploy and plugins. Leave a field empty to leave that type alone.</p>
            <div class="sm-group">Simultaneous transfers</div>
            <label class="check">Send up to <input name="max_connections" class="mono" style="width:60px;margin:0 6px" inputmode="numeric"> files at the same time (1–10)</label>
            <p class="muted sm-note">More is faster with many small files, especially on a slow connection. Lower it if the server complains about too many connections.</p>
          </div>
          <div class="sm-wide" data-proto="ftp">
            <div class="sm-group">Transfer mode</div>
            <label class="check"><input type="radio" name="transfer_mode" value="default"> Default</label>
            <label class="check"><input type="radio" name="transfer_mode" value="active"> Active</label>
            <label class="check"><input type="radio" name="transfer_mode" value="passive"> Passive</label>
            <div class="sm-group">TLS certificate</div>
            <label class="check"><input type="checkbox" name="ftps_insecure"> Accept the certificate even if it can't be verified</label>
            <p class="muted sm-note">Only needed when the server's certificate doesn't match the host name, which is common on shared hosting.</p>
          </div>
          <p class="muted sm-wide sm-note" data-proto="sftp">Transfer mode and TLS settings only apply to FTP.</p>
        </div>
        <div class="sm-page" data-page="charset">
          <div class="sm-wide" data-proto="ftp">
            <p class="muted sm-note">The server uses this character set to encode file names:</p>
            <label class="check"><input type="radio" name="cs_mode" value="auto"> Autodetect</label>
            <label class="check"><input type="radio" name="cs_mode" value="utf-8"> Force UTF-8</label>
            <label class="check"><input type="radio" name="cs_mode" value="custom"> Use custom charset</label>
            <label class="field sm-indent">Encoding:<input name="charset_custom" placeholder="e.g. latin-1 or cp1252"></label>
          </div>
          <p class="muted sm-wide" data-proto="sftp">SFTP always uses UTF-8 for file names.</p>
        </div>
      </form>
    </div>
  </div>`;

  // --- form <-> site ---
  function readForm() {
    const s = sel?.type === 'site' && siteById(sel.id);
    if (!s) return;
    for (const k of ['protocol', 'host', 'port', 'encryption', 'auth', 'username', 'key_path', 'color', 'comments', 'local_dir', 'remote_dir']) {
      s[k] = k === 'comments' ? E(k).value : E(k).value.trim();
    }
    s.transfer_mode = E('transfer_mode').value || 'default';
    s.ftps_insecure = E('ftps_insecure').checked;
    s.upload_perms = E('upload_perms').checked;
    s.upload_dir_mode = E('upload_dir_mode').value.trim();
    s.upload_file_mode = E('upload_file_mode').value.trim();
    s.max_connections = E('max_connections').value.trim() || '3';
    const cs = E('cs_mode').value || 'auto';
    s.charset = cs === 'custom' ? (E('charset_custom').value.trim() || 'auto') : cs;
    const sec = secrets[s.id] ||= {};
    if (E('password').value) sec.password = E('password').value;
    if (E('passphrase').value) sec.passphrase = E('passphrase').value;
  }
  function setLogonOptions(proto) {
    const a = E('auth');
    const cur = a.value;
    a.innerHTML = opt(LOGON_LABEL, LOGONS[proto]);
    a.value = LOGONS[proto].includes(cur) ? cur : 'password';
  }
  function applyVis() {
    const proto = E('protocol').value, auth = E('auth').value, enc = E('encryption').value;
    $$('#smForm [data-proto]', el).forEach(x => { x.hidden = x.dataset.proto !== proto || (!!x.dataset.enc && x.dataset.enc !== enc); });
    $$('#smForm [data-auth]', el).forEach(x => { x.hidden = !x.dataset.auth.split(' ').includes(auth); });
    E('port').placeholder = defaultPort({ protocol: proto, encryption: enc });
  }
  function fillForm() {
    const s = sel?.type === 'site' ? siteById(sel.id) : null;
    $('.sm-empty', el).hidden = !!s;
    $$('.sm-page', el).forEach(p => { p.hidden = !s || p.dataset.page !== tab; });
    $$('.sm-tab', el).forEach(t => { t.classList.toggle('active', !!s && t.dataset.tab === tab); t.disabled = !s; });
    if (!s) return;
    E('protocol').value = s.protocol || 'sftp';
    setLogonOptions(E('protocol').value);
    for (const k of ['host', 'username', 'key_path', 'comments', 'local_dir', 'remote_dir']) E(k).value = s[k] ?? '';
    E('port').value = s.port && +s.port !== defaultPort(s) ? s.port : '';
    E('encryption').value = s.encryption || 'auto';
    E('auth').value = LOGONS[E('protocol').value].includes(s.auth) ? s.auth : 'password';
    E('color').value = s.color || '';
    const sec = secrets[s.id] || {};
    E('password').value = '';
    E('password').placeholder = sec.password ? '•••••••• (new, saved on OK)' : s.has_password ? '•••••••• (saved – leave empty to keep)' : '';
    E('passphrase').value = '';
    E('passphrase').placeholder = sec.passphrase || s.has_passphrase ? '•••••••• (saved)' : 'only if your key has one';
    E('transfer_mode').value = s.transfer_mode || 'default';
    E('ftps_insecure').checked = !!s.ftps_insecure;
    E('upload_perms').checked = !!s.upload_perms;
    E('upload_dir_mode').value = s.upload_dir_mode ?? '0755';
    E('upload_file_mode').value = s.upload_file_mode ?? '0644';
    E('max_connections').value = s.max_connections ?? 3;
    const cs = s.charset || 'auto';
    E('cs_mode').value = ['auto', 'utf-8'].includes(cs) ? cs : 'custom';
    E('charset_custom').value = ['auto', 'utf-8'].includes(cs) ? '' : cs;
    applyVis();
  }

  // --- tree ---
  function renderTree() {
    const t = $('#smTree', el);
    const isSel = (type, v) => sel?.type === type && (type === 'site' ? sel.id === v : type === 'folder' ? sel.name === v : true);
    const siteRow = s => `<div class="sm-node sm-site ${isSel('site', s.id) ? 'active' : ''}" data-site="${esc(s.id)}" draggable="true">
      ${SERVER_ICON}<span>${esc(s.name)}</span>${s.color ? `<i class="sm-dot" style="background:var(--c-${s.color})"></i>` : ''}</div>`;
    const inFolder = f => work.filter(s => (s.folder || '') === f).sort(byName).map(siteRow).join('');
    t.innerHTML = `<div class="sm-node sm-folder ${isSel('root') ? 'active' : ''}" data-folder="">${ICON.dir}<span>My Sites</span></div>
      <div class="sm-children">
        ${allFolders().map(f => `<div class="sm-node sm-folder ${isSel('folder', f) ? 'active' : ''}" data-folder="${esc(f)}">${ICON.dir}<span>${esc(f)}</span></div>
          <div class="sm-children">${inFolder(f)}</div>`).join('')}
        ${inFolder('')}
      </div>`;
    $('[data-sm=rename]', el).disabled = !sel || sel.type === 'root';
    $('[data-sm=delete]', el).disabled = !sel || sel.type === 'root';
    $('[data-sm=duplicate]', el).disabled = sel?.type !== 'site';
  }
  function select(next) {
    readForm();
    sel = next;
    renderTree();
    fillForm();
  }
  const currentFolder = () => sel?.type === 'folder' ? sel.name : sel?.type === 'site' ? (siteById(sel.id)?.folder || '') : '';
  function uniqueName(base) {
    let n = base, i = 2;
    while (work.some(s => s.name === n)) n = `${base} ${i++}`;
    return n;
  }

  const actions = {
    async newsite() {
      readForm();
      const name = await askText('New site', 'Name of the new site', uniqueName('New site'));
      if (!name) return;
      const s = {
        id: `new-${++tempN}`, name: name.trim(), folder: currentFolder(), protocol: 'sftp', host: '', port: '',
        encryption: 'auto', auth: 'password', username: '', key_path: '', color: '', comments: '',
        local_dir: '', remote_dir: '', transfer_mode: 'default', charset: 'auto', ftps_insecure: false,
        bookmarks: [], deploy: {},
      };
      work.push(s);
      tab = 'general';
      select({ type: 'site', id: s.id });
      E('host').focus();
    },
    async newfolder() {
      readForm();
      const name = await askText('New folder', 'Folder name', 'New folder');
      if (!name?.trim()) return;
      if (!folders.includes(name.trim())) folders.push(name.trim());
      select({ type: 'folder', name: name.trim() });
    },
    async rename() {
      readForm();
      if (sel?.type === 'site') {
        const s = siteById(sel.id);
        const name = await askText('Rename site', 'New name', s.name);
        if (name?.trim()) { s.name = name.trim(); renderTree(); }
      } else if (sel?.type === 'folder') {
        const name = (await askText('Rename folder', 'New name', sel.name))?.trim();
        if (!name || name === sel.name) return;
        folders = folders.map(f => f === sel.name ? name : f);
        work.forEach(s => { if (s.folder === sel.name) s.folder = name; });
        if (!folders.includes(name)) folders.push(name);
        sel = { type: 'folder', name };
        renderTree();
      }
    },
    duplicate() {
      readForm();
      const s = siteById(sel.id);
      const copy = { ...structuredClone(s), id: `new-${++tempN}`, name: uniqueName(`${s.name} (copy)`) };
      copy.copy_from = s.id.startsWith('new-') ? s.copy_from : s.id;
      if (secrets[s.id]) secrets[copy.id] = { ...secrets[s.id] };
      work.push(copy);
      select({ type: 'site', id: copy.id });
    },
    async delete() {
      readForm();
      if (sel?.type === 'site') {
        const s = siteById(sel.id);
        if (!await confirmBox('Delete site', `Delete "${esc(s.name)}"? Its saved password is removed too (after you click OK).`, 'Delete', true)) return;
        work.splice(work.indexOf(s), 1);
        if (!s.id.startsWith('new-')) deleted.push(s.id);
        sel = null;
      } else if (sel?.type === 'folder') {
        const inside = work.filter(s => s.folder === sel.name);
        if (!await confirmBox('Delete folder', `Delete the folder "${esc(sel.name)}"${inside.length ? ` and the ${inside.length} site(s) in it` : ''}?`, 'Delete', true)) return;
        for (const s of inside) { work.splice(work.indexOf(s), 1); if (!s.id.startsWith('new-')) deleted.push(s.id); }
        folders = folders.filter(f => f !== sel.name);
        sel = null;
      }
      renderTree();
      fillForm();
    },
  };

  async function commit() {
    readForm();
    try {
      const r = await api('sites_apply', { sites: work, deleted, folders: allFolders(), secrets });
      S.sites = r.sites;
      S.folders = r.folders;
      const id = sel?.type === 'site' ? (r.ids[sel.id] || sel.id) : null;
      renderSites(id || undefined);
      if (id) store.set('site', id);
      return { ok: true, id };
    } catch (e) {
      modal({ title: 'Cannot save', body: `<p>${esc(e.message)}</p>`, buttons: [{ label: 'OK', value: null, primary: true }] });
      return { ok: false };
    }
  }

  return modal({
    title: 'Site Manager', body, size: 'sm-size',
    buttons: [
      { label: 'Connect', primary: true, onClick: async (m, close) => {
        if (sel?.type !== 'site') return toast('Select a site to connect to');
        const r = await commit();
        if (r.ok) { close('ok'); connect(); }
      } },
      { label: 'OK', onClick: async (m, close) => { if ((await commit()).ok) close('ok'); } },
      { label: 'Cancel', value: null },
    ],
    onOpen(m) {
      el = m;
      $('.sm-btns', el).addEventListener('click', e => { const a = e.target.closest('[data-sm]')?.dataset.sm; if (a) actions[a](); });
      $('.sm-tabs', el).addEventListener('click', e => {
        const t = e.target.closest('[data-tab]');
        if (!t || t.disabled) return;
        readForm(); tab = t.dataset.tab; fillForm();
      });
      const tree = $('#smTree', el);
      tree.addEventListener('click', e => {
        const n = e.target.closest('.sm-node');
        if (!n) return;
        if (n.dataset.site) select({ type: 'site', id: n.dataset.site });
        else select(n.dataset.folder ? { type: 'folder', name: n.dataset.folder } : { type: 'root' });
      });
      tree.addEventListener('dblclick', e => {
        const n = e.target.closest('.sm-site');
        if (n) $$('.mfoot button', el).find(b => b.textContent === 'Connect').click();
      });
      // drag a site onto a folder (or "My Sites") to move it
      tree.addEventListener('dragstart', e => { const n = e.target.closest('.sm-site'); if (n) e.dataTransfer.setData('text/x-fb-site', n.dataset.site); });
      tree.addEventListener('dragover', e => { if (e.target.closest('.sm-folder') && e.dataTransfer.types.includes('text/x-fb-site')) e.preventDefault(); });
      tree.addEventListener('drop', e => {
        const f = e.target.closest('.sm-folder');
        const s = siteById(e.dataTransfer.getData('text/x-fb-site'));
        if (!f || !s) return;
        e.preventDefault();
        readForm();
        s.folder = f.dataset.folder;
        renderTree();
      });
      // protocol / encryption / logon type change what is shown; reset the port if it was the default
      E('protocol').addEventListener('change', () => { setLogonOptions(E('protocol').value); applyVis(); });
      E('encryption').addEventListener('change', applyVis);
      E('auth').addEventListener('change', applyVis);
      E('charset_custom').addEventListener('input', () => { E('cs_mode').value = 'custom'; });
      ['upload_dir_mode', 'upload_file_mode'].forEach(n => E(n).addEventListener('input', () => { E('upload_perms').checked = true; }));

      const start = S.sites.find(s => s.id === (focusId || $('#siteSelect').value)) || S.sites[0];
      sel = start ? { type: 'site', id: start.id } : { type: 'root' };
      renderTree();
      fillForm();
    },
  });
}
const openSites = openSiteManager;
$('#btnSites').onclick = () => openSiteManager();

/* ---------------------------------------------------------------- bookmarks */
function bookmarksMenu(x, y) {
  const site = currentSite();
  const bms = site?.bookmarks || [];
  const items = [];
  if (!site) items.push({ header: 'Create a site first' });
  for (const b of bms) {
    items.push({ label: b.name, hint: [b.local && 'local', b.remote && 'server'].filter(Boolean).join(' + '), action: () => {
      if (b.local) PL.load(b.local);
      if (b.remote && S.status.connected) PR.load(b.remote);
    } });
  }
  if (site) {
    if (bms.length) items.push({ sep: true });
    items.push({ label: 'Bookmark current folders…', action: async () => {
      const name = await askText('Add bookmark', 'Name', baseName(PR.path || PL.path) || 'Bookmark');
      if (!name) return;
      const b = { name, local: PL.path, remote: S.status.connected ? PR.path : '' };
      const r = await api('site_update', { id: site.id, patch: { bookmarks: [...bms, b] } });
      S.sites = r.sites; toast('Bookmark added', 'ok');
    } });
    if (bms.length) items.push({ label: 'Remove a bookmark…', action: async () => {
      const name = await askText('Remove bookmark', 'Name of the bookmark to remove', bms.at(-1).name);
      if (!name) return;
      const r = await api('site_update', { id: site.id, patch: { bookmarks: bms.filter(b => b.name !== name) } });
      S.sites = r.sites;
    } });
  }
  showMenu(x, y, items);
}

/* ---------------------------------------------------------------- compare & sync */
const STATUS_LABEL = {
  local_only: 'Only local', remote_only: 'Only on server', local_newer: 'Local newer',
  remote_newer: 'Server newer', different: 'Different', same: 'Identical',
};
const ACTION_LABEL = { skip: 'Skip', upload: 'Upload →', download: '← Download', delete_remote: 'Delete on server', delete_local: 'Delete local' };

function defaultAction(status, dir, mirror) {
  if (status === 'same') return 'skip';
  if (dir === 'up') {
    if (status === 'remote_only') return mirror ? 'delete_remote' : 'skip';
    if (status === 'remote_newer') return mirror ? 'upload' : 'skip';
    return 'upload';
  }
  if (dir === 'down') {
    if (status === 'local_only') return mirror ? 'delete_local' : 'skip';
    if (status === 'local_newer') return mirror ? 'download' : 'skip';
    return 'download';
  }
  return { local_only: 'upload', local_newer: 'upload', remote_only: 'download', remote_newer: 'download' }[status] || 'skip';
}
function allowedActions(status) {
  return {
    local_only: ['skip', 'upload', 'delete_local'],
    remote_only: ['skip', 'download', 'delete_remote'],
    same: ['skip', 'upload', 'download'],
  }[status] || ['skip', 'upload', 'download'];
}

function openCompare() {
  if (!S.status.connected) return toast('Connect to a server first', 'error');
  let data = null;
  const body = `
    <div class="row">
      <label class="field">Local folder<span class="with-btn"><input id="cmpLocal" value="${esc(PL.path)}"><button type="button" data-pick="folder">Browse…</button></span></label>
      <label class="field">Server folder<span class="with-btn"><input id="cmpRemote" value="${esc(PR.path)}"><button type="button" data-current="remote" title="Use the folder that is open in the server pane">Use current</button></span></label>
    </div>
    <div class="row">
      <label class="field">Ignore (comma separated, wildcards allowed)<input id="cmpIgnore" value="${esc(store.get('ignore', S.ignore.join(', ')))}"></label>
      <button id="cmpRun" class="primary" style="margin-top:8px">Compare</button>
    </div>
    <div id="cmpOut"><p class="muted">Compares every file in both folders (including subfolders) by size and modification time.</p></div>`;
  modal({
    title: 'Compare & sync', body, size: 'wide',
    buttons: [{ label: 'Close', value: null }, { label: 'Run sync', id: 'cmpSync', primary: true, onClick: el => runSync(el) }],
    onOpen(el) {
      $('#cmpSync', el).disabled = true;
      $('#cmpRun', el).onclick = () => runCompare(el);
    },
  });

  async function runCompare(el) {
    const ignore = $('#cmpIgnore', el).value;
    store.set('ignore', ignore);
    $('#cmpOut', el).innerHTML = '<p class="muted">Scanning both folders… (see the queue for progress)</p>';
    $('#cmpSync', el).disabled = true;
    try {
      const r = await api('compare', { local: $('#cmpLocal', el).value.trim(), remote: $('#cmpRemote', el).value.trim(), ignore });
      watchJob(r.job_id, job => {
        if (job.status !== 'done') { $('#cmpOut', el).innerHTML = `<div class="info-box err">${esc(job.error || 'Cancelled')}</div>`; return; }
        data = job.result;
        data.dir = store.get('syncDir', 'up');
        data.mirror = false;
        data.hidden = new Set(['same']);
        data.rows.forEach(row => { row.action = defaultAction(row.status, data.dir, false); });
        renderCompare(el);
      });
    } catch (e) { $('#cmpOut', el).innerHTML = `<div class="info-box err">${esc(e.message)}</div>`; }
  }

  function renderCompare(el) {
    const out = $('#cmpOut', el);
    const c = data.counts;
    const chips = Object.keys(STATUS_LABEL).filter(k => c[k]).map(k =>
      `<span class="chip ${data.hidden.has(k) ? 'off' : ''}" data-st="${k}"><span class="st st-${k}">${STATUS_LABEL[k]}</span> ${c[k]}</span>`).join('');
    const rows = data.rows.filter(r => !data.hidden.has(r.status));
    out.innerHTML = `
      <div class="cmp-controls">
        <label class="inline">Direction
          <select id="cmpDir">
            <option value="up">Local → Server (upload changes)</option>
            <option value="down">Server → Local (download changes)</option>
            <option value="both">Both ways (newest wins)</option>
          </select></label>
        <label class="check" style="margin:0" title="Make the destination an exact copy: files that only exist there are deleted, and newer files there are overwritten.">
          <input type="checkbox" id="cmpMirror" ${data.mirror ? 'checked' : ''} ${data.dir === 'both' ? 'disabled' : ''}> Mirror (delete extra files)</label>
        <div class="spacer"></div>
        <div class="chips">${chips || '<span class="muted">No files found</span>'}</div>
      </div>
      ${rows.length ? `<div class="cmp-wrap"><table class="cmp-table">
        <thead><tr><th style="width:30px"></th><th>File</th><th style="width:110px">Status</th>
          <th style="width:150px">Local</th><th style="width:150px">Server</th><th style="width:140px">Action</th></tr></thead>
        <tbody>${rows.map(r => {
          const i = data.rows.indexOf(r);
          return `<tr data-i="${i}">
            <td class="c-chk"><input type="checkbox" ${r.action !== 'skip' ? 'checked' : ''}></td>
            <td title="${esc(r.path)}">${esc(r.path)}</td>
            <td><span class="st st-${r.status}">${STATUS_LABEL[r.status]}</span></td>
            <td class="muted">${r.local_size != null ? fmtSize(r.local_size) + ' · ' + fmtDate(r.local_mtime) : '—'}</td>
            <td class="muted">${r.remote_size != null ? fmtSize(r.remote_size) + ' · ' + fmtDate(r.remote_mtime) : '—'}</td>
            <td><select>${allowedActions(r.status).map(a => `<option value="${a}" ${a === r.action ? 'selected' : ''}>${ACTION_LABEL[a]}</option>`).join('')}</select></td>
          </tr>`;
        }).join('')}</tbody></table></div>`
        : `<div class="info-box">${!data.rows.length ? 'No files found.'
            : data.rows.every(r => r.status === 'same') ? `All ${c.same} file(s) are identical – nothing to sync.`
            : 'All differences are hidden – click the labels above to show them.'}</div>`}`;
    $('#cmpDir', out).value = data.dir;
    $('#cmpDir', out).onchange = e => {
      data.dir = e.target.value; store.set('syncDir', data.dir);
      if (data.dir === 'both') data.mirror = false;
      data.rows.forEach(r => { r.action = defaultAction(r.status, data.dir, data.mirror); });
      renderCompare(el);
    };
    $('#cmpMirror', out).onchange = e => {
      data.mirror = e.target.checked;
      data.rows.forEach(r => { r.action = defaultAction(r.status, data.dir, data.mirror); });
      renderCompare(el);
    };
    $$('.chip', out).forEach(ch => ch.onclick = () => {
      const k = ch.dataset.st;
      data.hidden.has(k) ? data.hidden.delete(k) : data.hidden.add(k);
      renderCompare(el);
    });
    out.querySelector('tbody')?.addEventListener('change', e => {
      const tr = e.target.closest('tr');
      const r = data.rows[+tr.dataset.i];
      if (e.target.matches('select')) r.action = e.target.value;
      else if (!e.target.checked) r.action = 'skip';
      else {
        const d = defaultAction(r.status, data.dir, true);
        r.action = d === 'skip' ? allowedActions(r.status)[1] : d;
      }
      renderCompare(el);
    });
    const n = data.rows.filter(r => r.action !== 'skip').length;
    const btn = $('#cmpSync', el);
    btn.disabled = !n;
    btn.textContent = n ? `Run sync (${n})` : 'Run sync';
  }

  async function runSync(el) {
    const items = data.rows.filter(r => r.action !== 'skip');
    if (!items.length) return;
    const dels = items.filter(r => r.action.startsWith('delete')).length;
    const counts = {};
    items.forEach(r => { counts[r.action] = (counts[r.action] || 0) + 1; });
    const summary = Object.entries(counts).map(([a, n]) => `${n} × ${ACTION_LABEL[a]}`).join('<br>');
    if (!await confirmBox('Run sync', `${summary}${dels ? '<br><br><b>Files deleted on the server cannot be recovered.</b> Local deletions go to the Trash.' : ''}`, 'Run sync', dels > 0)) return;
    try {
      const r = await api('sync', { local_root: data.local_root, remote_root: data.remote_root, items });
      $('#cmpSync', el).disabled = true;
      $('#cmpOut', el).innerHTML = '<p class="muted">Syncing… (see the queue for progress)</p>';
      watchJob(r.job_id, job => {
        if (job.status === 'done') { toast(job.result?.message || 'Sync finished', 'ok'); runCompare(el); }
        else $('#cmpOut', el).innerHTML = `<div class="info-box err">${esc(job.error || 'Cancelled')}</div>`;
      });
    } catch (e) { toast(e.message, 'error'); }
  }
}
$('#btnCompare').onclick = openCompare;

/* ---------------------------------------------------------------- deploy */
function openDeploy() {
  const site = currentSite();
  const cfg = { zip_path: '', zip_folder: '', zip_pattern: '*.zip', remote_dir: '', method: 'auto', backup: true, strip: true, ...(site?.deploy || {}) };
  if (!cfg.remote_dir) cfg.remote_dir = PR.path || site?.remote_dir || '';
  const mode = cfg.zip_path ? 'file' : (cfg.zip_folder ? 'newest' : 'file');
  const body = `
    <p class="muted" style="margin-top:0">Uploads a zip and unpacks it into a folder on the server, replacing existing files. Save the settings to the site and next time it's one click.</p>
    <label class="check"><input type="radio" name="zmode" value="file" ${mode === 'file' ? 'checked' : ''}> A specific zip file</label>
    <label class="field" data-z="file"><span class="with-btn"><input id="dZip" value="${esc(cfg.zip_path)}" placeholder="~/Downloads/update.zip"><button type="button" data-pick="file" data-types="zip">Browse…</button></span></label>
    <label class="check"><input type="radio" name="zmode" value="newest" ${mode === 'newest' ? 'checked' : ''}> The newest zip in a folder</label>
    <div class="row" data-z="newest">
      <label class="field" style="flex:3">Folder<span class="with-btn"><input id="dFolder" value="${esc(cfg.zip_folder)}" placeholder="~/Projects"><button type="button" data-pick="folder">Browse…</button></span></label>
      <label class="field" style="flex:2">File name pattern<input id="dPattern" value="${esc(cfg.zip_pattern)}" placeholder="site-update_*.zip"></label>
    </div>
    <label class="field">Server folder to deploy to<span class="with-btn"><input id="dRemote" value="${esc(cfg.remote_dir)}"><button type="button" data-current="remote" title="Use the folder that is open in the server pane">Use current</button></span></label>
    <div class="row">
      <label class="field">Unpack method
        <select id="dMethod">
          <option value="auto">Automatic (on server if possible)</option>
          <option value="server">On the server (fast, needs SSH + unzip)</option>
          <option value="local">Unpack locally, upload files</option>
        </select></label>
    </div>
    <label class="check"><input type="checkbox" id="dBackup" ${cfg.backup ? 'checked' : ''}> Make a backup of the server folder first</label>
    <label class="check"><input type="checkbox" id="dStrip" ${cfg.strip ? 'checked' : ''}> If the zip contains a single top folder, deploy its contents</label>
    <div id="dInfo"></div>`;
  modal({
    title: `Deploy${site ? ' – ' + site.name : ''}`, body, size: 'mid',
    buttons: [
      { label: 'Save to site', left: true, onClick: async el => {
        if (!site) return toast('Create a site first', 'error');
        const r = await api('site_update', { id: site.id, patch: { deploy: read(el) } });
        S.sites = r.sites; toast('Deploy settings saved', 'ok');
      } },
      { label: 'Close', value: null },
      { label: 'Deploy now', primary: true, onClick: (el, close) => go(el, close) },
    ],
    onOpen(el) {
      $('#dMethod', el).value = cfg.method;
      const vis = () => {
        const m = $('input[name=zmode]:checked', el).value;
        $$('[data-z]', el).forEach(x => { x.hidden = x.dataset.z !== m; });
        preview(el);
      };
      $$('input[name=zmode]', el).forEach(r => r.onchange = vis);
      ['#dZip', '#dFolder', '#dPattern'].forEach(s => $(s, el).addEventListener('change', () => preview(el)));
      vis();
    },
  });

  function read(el) {
    const m = $('input[name=zmode]:checked', el).value;
    return {
      zip_path: m === 'file' ? $('#dZip', el).value.trim() : '',
      zip_folder: m === 'newest' ? $('#dFolder', el).value.trim() : '',
      zip_pattern: $('#dPattern', el).value.trim() || '*.zip',
      remote_dir: $('#dRemote', el).value.trim(),
      method: $('#dMethod', el).value,
      backup: $('#dBackup', el).checked,
      strip: $('#dStrip', el).checked,
    };
  }
  async function preview(el) {
    const box = $('#dInfo', el);
    const c = read(el);
    if (!c.zip_path && !c.zip_folder) { box.innerHTML = ''; return null; }
    try {
      const { info } = await api('deploy_preview', { cfg: c });
      box.innerHTML = `<div class="info-box"><b>${esc(info.name)}</b> · ${fmtSize(info.size)} · ${fmtDate(info.mtime)} · ${info.files} files
        ${info.top_folder ? `<br>Top folder: <span class="mono">${esc(info.top_folder)}/</span>${c.strip ? ' (its contents will be deployed)' : ''}` : ''}
        <div class="mono muted" style="margin-top:6px">${info.sample.map(esc).join('<br>')}${info.files > info.sample.length ? '<br>…' : ''}</div></div>`;
      return info;
    } catch (e) { box.innerHTML = `<div class="info-box err">${esc(e.message)}</div>`; return null; }
  }
  async function go(el, close) {
    if (!S.status.connected) return toast('Connect to a server first', 'error');
    const c = read(el);
    const info = await preview(el);
    if (!info) return;
    if (!c.remote_dir) return toast('Fill in the server folder', 'error');
    if (!await confirmBox('Deploy', `Deploy <b>${esc(info.name)}</b> (${info.files} files) to<br><span class="mono">${esc(S.status.label)}:${esc(c.remote_dir)}</span>?<br><br>Existing files with the same name are overwritten.${c.backup ? ' A backup is made first.' : ' <b>No backup will be made.</b>'}`, 'Deploy')) return;
    try {
      const r = await api('deploy', { cfg: c });
      close('ok');
      watchJob(r.job_id, job => {
        if (job.status === 'done') showResult('Deploy finished', job.result?.message || 'Done');
      });
    } catch (e) { toast(e.message, 'error'); }
  }
}
$('#btnDeploy').onclick = openDeploy;

/* ---------------------------------------------------------------- plugins */
async function runPlugin(p, pane) {
  pane = p.side === 'local' ? PL : p.side === 'remote' ? PR : (pane || S.active || PL);
  if ((p.side === 'remote' || pane.remote) && !S.status.connected) return toast('Connect to a server first', 'error');
  const paths = pane.selectedPaths();
  if (p.needs_selection && !paths.length) return toast('Select one or more items first');
  let input = null;
  if (p.ask) {
    input = await askText(p.label, p.ask, p.default || '');
    if (input === null) return;
  }
  if (p.confirm && !await confirmBox(p.label, esc(p.confirm), 'Run')) return;
  try {
    const r = await api('plugin_run', { id: p.id, side: pane.side, cwd: pane.path, paths, input });
    watchJob(r.job_id, job => {
      const msg = job.result?.message;
      if (job.status === 'done' && msg) showResult(p.label, msg);
    });
  } catch (e) { toast(e.message, 'error'); }
}

$('#btnPlugins').onclick = e => {
  const r = e.target.getBoundingClientRect();
  const items = [];
  const groups = {};
  for (const p of S.plugins) (groups[p.plugin] ||= []).push(p);
  for (const [g, list] of Object.entries(groups)) {
    items.push({ header: g });
    for (const p of list) items.push({ label: p.label, hint: p.side === 'any' ? '' : p.side, action: () => runPlugin(p) });
  }
  if (!S.plugins.length) items.push({ header: 'No plugins installed' });
  items.push({ sep: true },
    { label: 'Reload plugins', action: async () => {
      const r2 = await api('plugins_reload');
      S.plugins = r2.plugins;
      r2.errors.length ? toast('Plugin errors: ' + r2.errors.join('; '), 'error') : toast(`${S.plugins.length} plugin action(s) loaded`, 'ok');
    } },
    { label: 'Open plugins folder', action: () => api('reveal', {}) });
  showMenu(r.left, r.bottom + 4, items);
};

/* ---------------------------------------------------------------- start */
const PL = new Pane('local');
const PR = new Pane('remote');
setActive(PL);

try { $('#year').textContent = new Date().getFullYear(); } catch { /* ignore */ }

(async function init() {
  const r = await api('init');
  S.sites = r.sites;
  S.folders = r.folders || [];
  S.platform = r.platform || {};
  document.body.classList.toggle('in-app', !!S.platform.window);
  S.plugins = r.plugins;
  S.home = r.home;
  S.ignore = r.ignore;
  renderSites();
  applyStatus(r.status);
  await PL.load(store.get('localPath', r.home));
  PR.render();
  if (r.status.connected) PR.load('');
  poll();
  PL.list.focus();
})().catch(e => toast(e.message, 'error'));
