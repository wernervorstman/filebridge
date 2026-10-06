'use strict';
/* FileBridge – interface language. English text is the key; NL and ES hold the translations.
   The language comes from Settings (Automatic follows the language of the computer / browser). */

const LANGS = { en: 'English', nl: 'Nederlands', es: 'Español' };
function resolveLang(setting) {
  if (setting in LANGS) return setting;
  const nav = (navigator.language || 'en').toLowerCase().slice(0, 2);
  return nav in LANGS ? nav : 'en';
}
let LANG = resolveLang((() => { try { return JSON.parse(localStorage.getItem('fb.lang')); } catch { return 'auto'; } })() || 'auto');
let LOCALE = { nl: 'nl-NL', es: 'es-ES' }[LANG];

/** Mac keys (⌘ ⌥ ⇧) as Windows and Linux show them: Ctrl+ Alt+ Shift+. */
const IS_MAC_UI = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || '');
const keyText = s => IS_MAC_UI ? s : String(s).replace(/⌘/g, 'Ctrl+').replace(/⌥-?/g, 'Alt+').replace(/⇧/g, 'Shift+');

/** Translate an English interface text; {name} placeholders are filled from vars. */
function t(s, vars) {
  let out = (LANG === 'nl' && NL[s]) || (LANG === 'es' && ES[s]) || s;
  if (vars) out = out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return keyText(out);
}

/** Translate the fixed texts in index.html (data-t, data-t-title, data-t-ph). */
function translateStatic(root = document) {
  document.documentElement.lang = LANG;
  root.querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  root.querySelectorAll('[data-t-title]').forEach(el => { el.title = t(el.dataset.tTitle); });
  root.querySelectorAll('[data-t-ph]').forEach(el => { el.placeholder = t(el.dataset.tPh); });
}

const NL = {};
const ES = {};
