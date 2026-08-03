/**
 * Formateo y normalización de RUT chileno (Delco).
 * Uso:
 *   DelcoRut.format('12345678K')  → '12.345.678-K'
 *   DelcoRut.normalize('12.345.678-K') → '12345678-K'
 *   DelcoRut.bind(inputEl)
 */
(function (global) {
  'use strict';

  function clean(value) {
    return String(value || '').replace(/[^0-9Kk]/g, '').toUpperCase();
  }

  function format(value) {
    var val = clean(value);
    if (!val) return '';
    if (val.length === 1) return val;
    var dv = val.slice(-1);
    var num = val.slice(0, -1);
    var formatted;
    if (num.length > 6) {
      formatted =
        num.slice(0, num.length - 6) +
        '.' +
        num.slice(num.length - 6, num.length - 3) +
        '.' +
        num.slice(num.length - 3) +
        '-' +
        dv;
    } else if (num.length > 3) {
      formatted = num.slice(0, num.length - 3) + '.' + num.slice(num.length - 3) + '-' + dv;
    } else {
      formatted = num + '-' + dv;
    }
    return formatted;
  }

  function normalize(value) {
    var val = clean(value);
    if (val.length < 2) return val;
    return val.slice(0, -1) + '-' + val.slice(-1);
  }

  function bind(input) {
    if (!input) return;
    input.addEventListener('input', function () {
      this.value = format(this.value);
    });
  }

  function bindAll(selector) {
    var nodes = document.querySelectorAll(selector || '[data-delco-rut]');
    for (var i = 0; i < nodes.length; i++) {
      bind(nodes[i]);
    }
  }

  global.DelcoRut = {
    format: format,
    normalize: normalize,
    clean: clean,
    bind: bind,
    bindAll: bindAll,
  };
})(typeof window !== 'undefined' ? window : this);
