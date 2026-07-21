/**
 * Autocomplete reutilizable DELCO.
 * Markup esperado:
 * <div class="delco-ac" data-ac-url="..." data-ac-hidden="#idHidden" data-ac-min="2">
 *   <input type="text" class="form-control delco-ac-input" autocomplete="off">
 *   <div class="delco-ac-results list-group ..."></div>
 * </div>
 * <input type="hidden" id="idHidden" name="...">
 */
(function (window, document) {
  'use strict';

  function ensureOption(selectEl, id, label) {
    if (!selectEl) return;
    var value = String(id);
    var exists = Array.prototype.some.call(selectEl.options, function (opt) {
      return opt.value === value;
    });
    if (!exists) {
      var opt = document.createElement('option');
      opt.value = value;
      opt.textContent = label || value;
      selectEl.appendChild(opt);
    }
    selectEl.value = value;
  }

  function initOne(root) {
    if (!root || root.dataset.acReady === '1') return;
    root.dataset.acReady = '1';

    var input = root.querySelector('.delco-ac-input');
    var results = root.querySelector('.delco-ac-results');
    var url = root.getAttribute('data-ac-url') || '';
    var minChars = parseInt(root.getAttribute('data-ac-min') || '2', 10) || 2;
    var hiddenSel = root.getAttribute('data-ac-hidden') || '';
    var selectSel = root.getAttribute('data-ac-select') || '';
    var hidden = hiddenSel ? document.querySelector(hiddenSel) : null;
    var selectEl = null;
    if (selectSel) {
      selectEl = document.querySelector(selectSel)
        || document.getElementById(selectSel.replace(/^#/, ''))
        || document.querySelector('#' + selectSel);
    }
    var timer = null;
    var abortCtrl = null;
    var onPick = root.getAttribute('data-ac-on-pick') || '';

    if (!input || !results || !url) return;

    function clearResults() {
      results.innerHTML = '';
      results.classList.add('d-none');
    }

    function pick(item) {
      var label = item.label || item.numero_cliente || item.nombre_interno || String(item.id);
      input.value = label;
      if (hidden) hidden.value = item.id;
      if (selectEl) ensureOption(selectEl, item.id, label);
      clearResults();
      if (onPick && typeof window[onPick] === 'function') {
        window[onPick](item, root);
      }
      input.dispatchEvent(new CustomEvent('delco-ac-pick', { detail: item, bubbles: true }));
    }

    function render(items) {
      results.innerHTML = '';
      if (!items || !items.length) {
        results.innerHTML = '<div class="list-group-item small text-muted">Sin resultados</div>';
        results.classList.remove('d-none');
        return;
      }
      items.forEach(function (item) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'list-group-item list-group-item-action py-2';
        btn.textContent = item.label || String(item.id);
        btn.addEventListener('click', function () { pick(item); });
        results.appendChild(btn);
      });
      results.classList.remove('d-none');
    }

    function search(q) {
      if (abortCtrl) abortCtrl.abort();
      abortCtrl = new AbortController();
      fetch(url + (url.indexOf('?') >= 0 ? '&' : '?') + 'q=' + encodeURIComponent(q), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        signal: abortCtrl.signal,
      })
        .then(function (r) { return r.json(); })
        .then(function (data) { render((data && data.results) || []); })
        .catch(function (err) {
          if (err && err.name === 'AbortError') return;
          clearResults();
        });
    }

    input.addEventListener('input', function () {
      var q = (input.value || '').trim();
      if (hidden && !q) hidden.value = '';
      if (q.length < minChars) {
        clearResults();
        return;
      }
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { search(q); }, 250);
    });

    input.addEventListener('focus', function () {
      var q = (input.value || '').trim();
      if (q.length >= minChars && results.children.length) {
        results.classList.remove('d-none');
      }
    });

    document.addEventListener('click', function (ev) {
      if (!root.contains(ev.target)) clearResults();
    });
  }

  function initDelcoAutocompletes(scope) {
    var root = scope || document;
    root.querySelectorAll('.delco-ac').forEach(initOne);
    // Compatibilidad con markup inventario existente
    root.querySelectorAll('.inventario-ac').forEach(function (el) {
      if (!el.classList.contains('delco-ac')) el.classList.add('delco-ac');
      var input = el.querySelector('.inventario-ac-input');
      if (input && !input.classList.contains('delco-ac-input')) input.classList.add('delco-ac-input');
      var res = el.querySelector('.inventario-ac-results');
      if (res && !res.classList.contains('delco-ac-results')) res.classList.add('delco-ac-results');
      initOne(el);
    });
  }

  window.initDelcoAutocompletes = initDelcoAutocompletes;
  document.addEventListener('DOMContentLoaded', function () {
    initDelcoAutocompletes(document);
  });
})(window, document);
