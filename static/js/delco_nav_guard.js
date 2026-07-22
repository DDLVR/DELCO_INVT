/**
 * Primer click gana en navegación del menú.
 * - El primer click en .app-nav-link dispara la navegación.
 * - Clicks siguientes siguen siendo interactivos (feedback visual)
 *   pero no envían más peticiones de página hasta que cargue la nueva.
 * - Ctrl/Cmd/Shift/middle-click y target=_blank no se bloquean.
 */
(function () {
  'use strict';

  if (window.__delcoNavGuardInstalled) return;
  window.__delcoNavGuardInstalled = true;

  var pendingHref = null;

  function normalizeHref(href) {
    if (!href) return '';
    try {
      return new URL(href, window.location.href).href;
    } catch (e) {
      return href;
    }
  }

  function isSamePage(href) {
    try {
      var next = new URL(href, window.location.href);
      var cur = window.location;
      return next.pathname === cur.pathname && next.search === cur.search && next.hash === cur.hash;
    } catch (e) {
      return false;
    }
  }

  function markPending(link) {
    document.querySelectorAll('a.app-nav-link.delco-nav-pending').forEach(function (el) {
      el.classList.remove('delco-nav-pending');
    });
    if (link) link.classList.add('delco-nav-pending');
  }

  function resetGuard() {
    pendingHref = null;
    document.body.classList.remove('delco-navigating');
    document.querySelectorAll('a.app-nav-link.delco-nav-pending').forEach(function (el) {
      el.classList.remove('delco-nav-pending');
    });
  }

  document.addEventListener(
    'click',
    function (ev) {
      if (ev.defaultPrevented) return;
      if (ev.button !== 0) return;
      if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;

      var link = ev.target && ev.target.closest ? ev.target.closest('a.app-nav-link') : null;
      if (!link) return;

      var href = link.getAttribute('href');
      if (!href || href.charAt(0) === '#' || href.indexOf('javascript:') === 0) return;
      if (link.getAttribute('target') === '_blank' || link.hasAttribute('download')) return;
      if (isSamePage(href)) return;

      var abs = normalizeHref(href);

      if (pendingHref) {
        // Ya hay una navegación en curso: permitir el click visual, sin nueva petición.
        ev.preventDefault();
        ev.stopPropagation();
        markPending(link);
        return;
      }

      pendingHref = abs;
      document.body.classList.add('delco-navigating');
      markPending(link);
      // Dejar que el navegador siga con la primera navegación.
    },
    true
  );

  // Si el usuario vuelve con el botón Atrás (bfcache), liberar el candado.
  window.addEventListener('pageshow', function (ev) {
    if (ev.persisted) resetGuard();
  });

  window.addEventListener('pagehide', function () {
    // Mantener pending durante la transición; se limpia al cargar la nueva página.
  });
})();
