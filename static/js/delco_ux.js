/**
 * UX DELCO: scroll suave, botón volver arriba, anclas en #delcoMainContent.
 * El scroll real de la app es el <main>, no window.
 */
(function () {
  'use strict';

  function prefersReducedMotion() {
    try {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    } catch (e) {
      return false;
    }
  }

  function getScrollRoot() {
    return document.getElementById('delcoMainContent') || document.scrollingElement || document.documentElement;
  }

  function scrollTopSmooth(root) {
    if (!root) return;
    if (prefersReducedMotion() || typeof root.scrollTo !== 'function') {
      root.scrollTop = 0;
      return;
    }
    root.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function initBackToTop() {
    var btn = document.getElementById('delcoBackToTop');
    var root = getScrollRoot();
    if (!btn || !root) return;

    var threshold = 280;
    var ticking = false;

    function update() {
      ticking = false;
      var y = root.scrollTop || 0;
      btn.classList.toggle('is-visible', y > threshold);
      btn.setAttribute('aria-hidden', y > threshold ? 'false' : 'true');
    }

    root.addEventListener(
      'scroll',
      function () {
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(update);
      },
      { passive: true }
    );

    btn.addEventListener('click', function (ev) {
      ev.preventDefault();
      scrollTopSmooth(root);
      try {
        btn.blur();
      } catch (e) { /* ignore */ }
    });

    update();
  }

  function initSmoothAnchors() {
    var root = getScrollRoot();
    if (!root) return;

    document.addEventListener('click', function (ev) {
      var a = ev.target && ev.target.closest ? ev.target.closest('a[href^="#"]') : null;
      if (!a) return;
      var href = a.getAttribute('href') || '';
      if (href === '#' || href.length < 2) return;
      if (a.hasAttribute('data-bs-toggle') || a.getAttribute('role') === 'button') return;

      var id = href.slice(1);
      var target = null;
      try {
        target = document.getElementById(decodeURIComponent(id));
      } catch (e) {
        return;
      }
      if (!target || !root.contains(target)) return;

      ev.preventDefault();
      if (prefersReducedMotion()) {
        target.scrollIntoView({ block: 'start' });
      } else {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }

  function initMobileNavPolish() {
    var offcanvasEl = document.getElementById('delcoSidebarOffcanvas');
    if (!offcanvasEl) return;

    // Cerrar al tocar fuera del menú (Bootstrap ya lo hace) + feedback táctil
    offcanvasEl.querySelectorAll('.app-nav-link').forEach(function (link) {
      link.addEventListener(
        'touchstart',
        function () {
          link.classList.add('delco-nav-touch');
        },
        { passive: true }
      );
      link.addEventListener(
        'touchend',
        function () {
          var el = link;
          setTimeout(function () {
            el.classList.remove('delco-nav-touch');
          }, 180);
        },
        { passive: true }
      );
    });
  }

  function initPageEnter() {
    if (prefersReducedMotion()) return;
    var main = document.getElementById('delcoMainContent');
    if (!main) return;
    main.classList.add('delco-page-enter');
  }

  document.addEventListener('DOMContentLoaded', function () {
    initBackToTop();
    initSmoothAnchors();
    initMobileNavPolish();
    initPageEnter();
  });

  window.delcoScrollToTop = function () {
    scrollTopSmooth(getScrollRoot());
  };
})();
