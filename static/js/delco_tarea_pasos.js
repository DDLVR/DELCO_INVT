(function () {
  var TEXTOS = {
    1: 'Elige el formulario que hay que llenar.',
    2: 'Escribe el título del trabajo. El cliente y el proyecto son opcionales.',
    3: 'Elige al menos un técnico o un grupo.',
    4: 'Revisa el mensaje y cuándo llega. Si el mensaje queda vacío, se usa el título.',
    5: 'La ubicación es opcional. Puedes continuar sin completarla.',
    6: 'Precarga lo que ya conoces y crea la tarea.'
  };

  function valor(form, selector) {
    var el = form.querySelector(selector);
    return el ? String(el.value || '').trim() : '';
  }

  function flags(form) {
    return String(form.getAttribute('data-paso-seguir') || '').split(',').filter(Boolean);
  }

  function pasoVisible(form) {
    var formId = valor(form, '[data-paso-campo="formulario"]');
    var titulo = valor(form, '[data-paso-campo="titulo"]');
    var recipients = !!form.querySelector('input[name="usuarios"]:checked, input[name="grupos"]:checked');
    var envio = valor(form, '[data-paso-campo="envio"]') || 'IMMEDIATE';
    var programada = valor(form, '[data-paso-campo="programada"]');
    var mensaje = valor(form, '[data-paso-campo="mensaje"]');
    var lugar = valor(form, '[data-paso-campo="ubicacion"]') || valor(form, '[name="latitud"]') || valor(form, '[name="longitud"]');
    var hechos = flags(form);
    var max = 1;
    if (formId) max = 2;
    if (max >= 2 && titulo) max = 3;
    if (max >= 3 && recipients) max = 4;
    var envioListo = envio !== 'SCHEDULED' || !!programada;
    if (max >= 4 && envioListo && (!!mensaje || hechos.indexOf('4') !== -1)) max = 5;
    if (max >= 5 && (!!lugar || hechos.indexOf('5') !== -1)) max = 6;
    return max;
  }

  function refresh(form) {
    if (!form) return;
    var max = pasoVisible(form);
    var previo = parseInt(form.getAttribute('data-paso-max') || '0', 10);
    form.querySelectorAll('[data-paso]').forEach(function (sec) {
      var n = parseInt(sec.getAttribute('data-paso'), 10);
      if (n <= max) sec.removeAttribute('hidden');
      else sec.setAttribute('hidden', '');
    });
    form.querySelectorAll('[data-paso-marca]').forEach(function (li) {
      var n = parseInt(li.getAttribute('data-paso-marca'), 10);
      li.classList.toggle('is-listo', n < max);
      li.classList.toggle('is-actual', n === max);
    });
    var enviar = form.querySelector('[data-paso-enviar]');
    if (enviar) {
      if (max >= 6) enviar.removeAttribute('hidden');
      else enviar.setAttribute('hidden', '');
    }
    var status = form.querySelector('[data-paso-status]');
    if (status) status.textContent = TEXTOS[max] || TEXTOS[1];
    form.setAttribute('data-paso-max', String(max));
    if (previo && max > previo) {
      var sec = form.querySelector('[data-paso="' + max + '"]');
      if (sec && sec.scrollIntoView) sec.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }

  function bind(form) {
    if (!form) return;
    if (form.getAttribute('data-pasos-listo') === '1') {
      refresh(form);
      return;
    }
    form.setAttribute('data-pasos-listo', '1');
    form.addEventListener('input', function () { refresh(form); });
    form.addEventListener('change', function (ev) {
      var campo = ev.target && ev.target.getAttribute ? ev.target.getAttribute('data-paso-campo') : '';
      if (campo === 'formulario') form.removeAttribute('data-paso-seguir');
      refresh(form);
    });
    form.addEventListener('click', function (ev) {
      var btn = ev.target && ev.target.closest ? ev.target.closest('[data-paso-continuar]') : null;
      if (!btn || !form.contains(btn)) return;
      var n = btn.getAttribute('data-paso-continuar');
      var aviso = form.querySelector('[data-paso-aviso="' + n + '"]');
      if (n === '4') {
        var envio = valor(form, '[data-paso-campo="envio"]') || 'IMMEDIATE';
        if (envio === 'SCHEDULED' && !valor(form, '[data-paso-campo="programada"]')) {
          if (aviso) {
            aviso.textContent = 'Indica la fecha y hora programadas para continuar.';
            aviso.classList.remove('d-none');
          }
          return;
        }
      }
      if (aviso) aviso.classList.add('d-none');
      var hechos = flags(form);
      if (hechos.indexOf(n) === -1) hechos.push(n);
      form.setAttribute('data-paso-seguir', hechos.join(','));
      refresh(form);
    });
    refresh(form);
  }

  function boot() {
    document.querySelectorAll('form[data-tarea-pasos]').forEach(bind);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();

  window.DelcoTareaPasos = {
    refresh: function (form) {
      bind(form || document.querySelector('form[data-tarea-pasos]'));
    }
  };
})();
