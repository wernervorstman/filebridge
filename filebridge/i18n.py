"""Language of the messages the server sends to the interface (errors, job titles, log lines).

The interface sends its language with every request (header X-Lang); background jobs keep the language of
the request that started them. The English text is the key, {name} placeholders are filled in by tr().
The Dutch and Spanish texts are in i18n_nl.py and i18n_es.py.
"""
import threading

LANGS = ('en', 'nl', 'es')
_local = threading.local()
_default = {'lang': 'en'}  # the language of the last request: for threads that weren't started by one


def set_lang(code):
    """Use this language in the current thread (and as the default for other threads)."""
    code = (code or '').lower()[:2]
    if code not in LANGS:
        code = 'en'
    _local.lang = code
    _default['lang'] = code


def use(code):
    """Use a language in this thread only (a job running for a request in that language)."""
    _local.lang = code if code in LANGS else 'en'


def current():
    return getattr(_local, 'lang', None) or _default['lang']


def tr(text, **kw):
    """Translate an English message to the current language and fill in {placeholders}."""
    lang = current()
    if lang != 'en':
        from . import i18n_es, i18n_nl
        text = {'nl': i18n_nl.NL, 'es': i18n_es.ES}[lang].get(text, text)
    if kw:
        try:
            text = text.format(**kw)
        except (KeyError, IndexError, ValueError):
            pass
    return text
