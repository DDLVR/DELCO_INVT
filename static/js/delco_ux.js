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

  function textoOpcion(opt) {
    return (opt.text || opt.textContent || '').trim();
  }

  function compararLista(a, b) {
    return textoOpcion(a).localeCompare(textoOpcion(b), 'es', { sensitivity: 'base', numeric: true });
  }

  function ordenarContenedor(nodo) {
    var opciones = [];
    var grupos = [];
    var hijos = nodo.children;
    var i;
    for (i = 0; i < hijos.length; i++) {
      if (hijos[i].tagName === 'OPTION') opciones.push(hijos[i]);
      else if (hijos[i].tagName === 'OPTGROUP') grupos.push(hijos[i]);
    }
    var fijas = [];
    var movibles = [];
    opciones.forEach(function (opt) {
      if (!opt.value) fijas.push(opt);
      else movibles.push(opt);
    });
    movibles.sort(compararLista);
    grupos.forEach(ordenarContenedor);
    if (nodo.tagName === 'SELECT' && nodo.selectedIndex >= 0 && nodo.options[nodo.selectedIndex]) {
      nodo.options[nodo.selectedIndex].selected = true;
    }
    var deseado = fijas.concat(movibles, grupos);
    var igual = deseado.length === hijos.length;
    for (i = 0; igual && i < deseado.length; i++) {
      if (hijos[i] !== deseado[i]) igual = false;
    }
    if (igual) return;
    deseado.forEach(function (hijo) { nodo.appendChild(hijo); });
  }

  function ordenarListas(raiz) {
    var scope = raiz && raiz.querySelectorAll ? raiz : document;
    var selects = scope.querySelectorAll('select, datalist');
    Array.prototype.forEach.call(selects, function (lista) {
      if (lista.dataset && lista.dataset.ordenLista === 'no') return;
      ordenarContenedor(lista);
    });
  }

  function initListasAlfabeticas() {
    ordenarListas(document);
    if (!window.MutationObserver || !document.body) return;
    var timer = 0;
    var observer = new MutationObserver(function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(ordenarListas, 40);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  document.addEventListener('DOMContentLoaded', function () {
    initBackToTop();
    initSmoothAnchors();
    initMobileNavPolish();
    initPageEnter();
    initListasAlfabeticas();
  });

  window.delcoScrollToTop = function () {
    scrollTopSmooth(getScrollRoot());
  };
})();
