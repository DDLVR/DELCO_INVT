/**
 * Navegación del shell Delco: navbar y menú lateral se quedan.
 * Solo el contenido se reemplaza. Mientras llega la página, un círculo gira
 * en el área principal y el menú sigue usable (otro click cancela la espera).
 */
(function () {
  'use strict';

  if (window.__delcoNavGuardInstalled) return;
  window.__delcoNavGuardInstalled = true;

  var pendingHref = null;
  var inflight = null;
  var pageTimers = [];
  var pageListeners = [];
  var nativeSetInterval = window.setInterval;
  var nativeSetTimeout = window.setTimeout;
  var nativeClearInterval = window.clearInterval;
  var nativeClearTimeout = window.clearTimeout;
  var nativeDocAdd = Document.prototype.addEventListener;
  var nativeWinAdd = Window.prototype.addEventListener;

  function $(id) {
    return document.getElementById(id);
  }

  function mainEl() {
    return $('delcoMainContent');
  }

  function loaderEl() {
    return $('delcoPageLoader');
  }

  function scriptsHost() {
    return $('delcoPageScripts');
  }

  function normalizeHref(href) {
    if (!href) return '';
    try {
      return new URL(href, window.location.href).href;
    } catch (e) {
      return href;
    }
  }

  function sameOrigin(url) {
    try {
      return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
      return false;
    }
  }

  function currentKey() {
    return window.location.pathname + window.location.search;
  }

  function urlKey(href) {
    try {
      var u = new URL(href, window.location.href);
      return u.pathname + u.search;
    } catch (e) {
      return href;
    }
  }

  function isFullPageUrl(href) {
    var path = '';
    try {
      path = new URL(href, window.location.href).pathname.toLowerCase();
    } catch (e) {
      return true;
    }
    if (/\/(login|logout|salir)\b/.test(path)) return true;
    if (/\.(pdf|xlsx|xls|csv|zip|png|jpe?g|gif|webp)$/.test(path)) return true;
    if (/exportar|download|descargar|\/pdf\/?$/.test(path)) return true;
    return false;
  }

  function shouldSkipLink(link, href) {
    if (!link || !href) return true;
    if (href.charAt(0) === '#') return true;
    if (href.indexOf('javascript:') === 0) return true;
    if (link.getAttribute('target') && link.getAttribute('target') !== '_self') return true;
    if (link.hasAttribute('download')) return true;
    if (link.getAttribute('data-delco-full-nav') === '1') return true;
    if (link.getAttribute('data-bs-toggle') && !link.classList.contains('app-nav-link')) return true;
    if (link.getAttribute('data-bs-dismiss')) return true;
    if (!sameOrigin(href)) return true;
    if (isFullPageUrl(href)) return true;
    return false;
  }

  function markPending(link) {
    document.querySelectorAll('a.delco-nav-pending').forEach(function (el) {
      el.classList.remove('delco-nav-pending');
    });
    if (link) link.classList.add('delco-nav-pending');
  }

  function setBusy(on) {
    document.body.classList.toggle('delco-navigating', !!on);
    var loader = loaderEl();
    var main = mainEl();
    if (loader) {
      loader.hidden = !on;
      loader.setAttribute('aria-hidden', on ? 'false' : 'true');
    }
    if (main) main.setAttribute('aria-busy', on ? 'true' : 'false');
  }

  function resetGuard() {
    pendingHref = null;
    setBusy(false);
    markPending(null);
  }

  function clearPageEffects() {
    var cleanups = (window.__delcoPageCleanup || []).splice(0);
    cleanups.forEach(function (fn) {
      try { fn(); } catch (e) { /* ignore */ }
    });
    pageTimers.forEach(function (item) {
      if (item.kind === 'interval') nativeClearInterval(item.id);
      else nativeClearTimeout(item.id);
    });
    pageTimers = [];
    pageListeners.forEach(function (item) {
      try {
        item.target.removeEventListener(item.type, item.fn, item.opts);
      } catch (e) { /* ignore */ }
    });
    pageListeners = [];
    var main = mainEl();
    ['modalLoteCsv', 'modalLoteClientes', 'modalLoteListado', 'modalNuevaTarea'].forEach(function (id) {
      Array.prototype.slice.call(document.querySelectorAll('#' + id)).forEach(function (el) {
        if (main && main.contains(el)) return;
        el.remove();
      });
    });
    document.querySelectorAll('.modal-backdrop').forEach(function (el) {
      el.remove();
    });
    document.body.classList.remove('modal-open');
    document.body.style.removeProperty('overflow');
    document.body.style.removeProperty('padding-right');
  }

  function trapPageSideEffects() {
    window.setInterval = function () {
      var id = nativeSetInterval.apply(window, arguments);
      pageTimers.push({ kind: 'interval', id: id });
      return id;
    };
    window.setTimeout = function () {
      var id = nativeSetTimeout.apply(window, arguments);
      pageTimers.push({ kind: 'timeout', id: id });
      return id;
    };
    function wrapAdd(proto, nativeFn, targetHint) {
      proto.addEventListener = function (type, fn, opts) {
        if (type === 'DOMContentLoaded' || type === 'readystatechange') {
          try { fn.call(this); } catch (e) { console.error(e); }
          return;
        }
        if (type === 'load' && (this === window || this === document)) {
          try { fn.call(this); } catch (e) { console.error(e); }
          return;
        }
        pageListeners.push({
          target: targetHint || this,
          type: type,
          fn: fn,
          opts: opts,
        });
        return nativeFn.call(this, type, fn, opts);
      };
    }
    wrapAdd(Document.prototype, nativeDocAdd, document);
    wrapAdd(Window.prototype, nativeWinAdd, window);
  }

  function untrapPageSideEffects() {
    window.setInterval = nativeSetInterval;
    window.setTimeout = nativeSetTimeout;
    Document.prototype.addEventListener = nativeDocAdd;
    Window.prototype.addEventListener = nativeWinAdd;
  }

  function runScriptsIn(root) {
    if (!root) return Promise.resolve();
    var list = Array.prototype.slice.call(root.querySelectorAll('script'));
    return list.reduce(function (chain, old) {
      return chain.then(function () {
        return new Promise(function (resolve) {
          var s = document.createElement('script');
          Array.prototype.forEach.call(old.attributes || [], function (attr) {
            s.setAttribute(attr.name, attr.value);
          });
          s.text = old.textContent || '';
          s.onload = function () { resolve(); };
          s.onerror = function () { resolve(); };
          if (old.parentNode) old.parentNode.replaceChild(s, old);
          else resolve();
          if (!s.src) resolve();
        });
      });
    }, Promise.resolve());
  }

  function syncSidebar(newDoc) {
    ['delcoSidebarDesktop', 'delcoSidebarOffcanvas'].forEach(function (id) {
      var cur = $(id);
      var next = newDoc.getElementById(id);
      if (!cur || !next) return;
      var curLinks = cur.querySelectorAll('a.app-nav-link');
      var nextLinks = next.querySelectorAll('a.app-nav-link');
      var n = Math.min(curLinks.length, nextLinks.length);
      for (var i = 0; i < n; i++) {
        curLinks[i].className = nextLinks[i].className;
      }
    });
  }

  function showPageMessages(newDoc) {
    var box = newDoc.getElementById('delcoPageMessages');
    if (!box || typeof window.showToast !== 'function') return;
    Array.prototype.forEach.call(box.querySelectorAll('[data-level]'), function (el) {
      window.showToast(el.textContent || '', el.getAttribute('data-level') || 'info');
    });
  }

  function applyPage(html, finalUrl, historyMode) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(html, 'text/html');
    var newMain = doc.getElementById('delcoMainContent');
    var main = mainEl();
    if (!newMain || !main || !doc.querySelector('nav.navbar')) {
      window.location.assign(finalUrl);
      return Promise.resolve();
    }

    clearPageEffects();
    main.innerHTML = newMain.innerHTML;
    main.scrollTop = 0;

    var host = scriptsHost();
    var newScripts = doc.getElementById('delcoPageScripts');
    if (host) {
      host.innerHTML = newScripts ? newScripts.innerHTML : '';
    }

    document.title = doc.title || document.title;
    syncSidebar(doc);
    main.classList.remove('delco-page-enter');
    void main.offsetWidth;
    main.classList.add('delco-page-enter');

    if (historyMode === 'push') {
      window.history.pushState({ delcoShell: 1 }, '', finalUrl);
    } else if (historyMode === 'replace') {
      window.history.replaceState({ delcoShell: 1 }, '', finalUrl);
    }

    trapPageSideEffects();
    return runScriptsIn(main)
      .then(function () { return runScriptsIn(host); })
      .then(function () {
        untrapPageSideEffects();
        showPageMessages(doc);
        if (typeof window.delcoScrollToTop === 'function') window.delcoScrollToTop();
        try {
          window.dispatchEvent(new CustomEvent('delco:page-ready', { detail: { url: finalUrl } }));
        } catch (e) { /* ignore */ }
      })
      .catch(function (err) {
        untrapPageSideEffects();
        throw err;
      });
  }

  function visit(href, opts) {
    opts = opts || {};
    var abs = normalizeHref(href);
    if (!abs) return;
    if (urlKey(abs) === currentKey() && opts.history !== 'none') {
      return;
    }

    if (inflight && inflight.abort) {
      try { inflight.abort(); } catch (e) { /* ignore */ }
    }

    pendingHref = abs;
    setBusy(true);
    markPending(opts.link || null);

    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    inflight = controller;

    fetch(abs, {
      method: 'GET',
      credentials: 'same-origin',
      redirect: 'follow',
      headers: { Accept: 'text/html' },
      signal: controller ? controller.signal : undefined,
    })
      .then(function (resp) {
        var finalUrl = resp.url || abs;
        if (/\/login\b/i.test(finalUrl) || resp.status === 401) {
          window.location.assign(finalUrl);
          return null;
        }
        var ctype = (resp.headers.get('content-type') || '').toLowerCase();
        if (ctype.indexOf('text/html') === -1) {
          window.location.assign(finalUrl);
          return null;
        }
        return resp.text().then(function (html) {
          return { html: html, finalUrl: finalUrl };
        });
      })
      .then(function (pack) {
        if (!pack) return;
        if (pendingHref !== abs) return;
        var historyMode = opts.history || 'push';
        return applyPage(pack.html, pack.finalUrl, historyMode);
      })
      .catch(function (err) {
        if (err && err.name === 'AbortError') return;
        if (typeof window.showToast === 'function') {
          window.showToast('No se pudo cargar la página. Reintenta.', 'danger');
        }
      })
      .then(function () {
        if (pendingHref === abs) resetGuard();
      });
  }

  document.addEventListener(
    'click',
    function (ev) {
      if (ev.defaultPrevented) return;
      if (ev.button !== 0) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;

      var link = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
      if (!link) return;

      var href = link.getAttribute('href');
      if (shouldSkipLink(link, href)) return;
      if (link.hash && urlKey(href) === currentKey()) return;

      ev.preventDefault();
      visit(href, { link: link, history: 'push' });
    },
    true
  );

  document.addEventListener('submit', function (ev) {
    var form = ev.target;
    if (!form || form.tagName !== 'FORM') return;
    if ((form.getAttribute('method') || 'get').toLowerCase() !== 'get') return;
    if (form.getAttribute('data-delco-full-nav') === '1') return;
    if (form.getAttribute('target') && form.getAttribute('target') !== '_self') return;
    var action = form.getAttribute('action') || window.location.href;
    if (!sameOrigin(action) || isFullPageUrl(action)) return;

    ev.preventDefault();
    var url = new URL(action, window.location.href);
    var data = new FormData(form);
    var params = new URLSearchParams(data);
    url.search = params.toString();
    visit(url.href, { history: 'push' });
  });

  window.addEventListener('popstate', function () {
    visit(window.location.href, { history: 'none' });
  });

  window.addEventListener('pageshow', function (ev) {
    if (ev.persisted) resetGuard();
  });

  window.delcoVisit = function (href) {
    visit(href, { history: 'push' });
  };
})();
