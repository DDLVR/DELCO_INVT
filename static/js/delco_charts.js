/**
 * Paletas de color compartidas para Chart.js y badges (Delco).
 * Alineadas con Bootstrap 5.3 + tokens de marca.
 */
(function (global) {
  'use strict';

  var BOOTSTRAP = {
    primary: '#0d6efd',
    success: '#198754',
    info: '#0dcaf0',
    warning: '#ffc107',
    danger: '#dc3545',
    secondary: '#6c757d',
    dark: '#212529',
    purple: '#5b5bd6',
    cyan: '#0891b2',
    navy: '#1a3a5c',
  };

  var ESTADO_SYNC_COLORS = {
    PROCESADO: BOOTSTRAP.success,
    EXITOSO: BOOTSTRAP.success,
    ALERTA_REVISION: BOOTSTRAP.warning,
    DUPLICADO: BOOTSTRAP.secondary,
    ERROR_JSON: BOOTSTRAP.danger,
    ERROR_LECTURA: BOOTSTRAP.danger,
    ERROR: BOOTSTRAP.danger,
    PENDIENTE: BOOTSTRAP.info,
  };

  var ESTADO_REVISION_COLORS = {
    REVISADO: BOOTSTRAP.success,
    CON_ADVERTENCIA: BOOTSTRAP.warning,
    DESCARTADO: BOOTSTRAP.secondary,
    PENDIENTE: BOOTSTRAP.primary,
  };

  var MOV_TIPO_COLORS = {
    ENTREGA: BOOTSTRAP.success,
    RECEPCION: BOOTSTRAP.info,
    INSTALACION: BOOTSTRAP.primary,
    RETIRO: BOOTSTRAP.warning,
    DEVOLUCION: BOOTSTRAP.danger,
    IMPORTACION: BOOTSTRAP.purple,
    MOREAPP: BOOTSTRAP.cyan,
    ELIMINACION: BOOTSTRAP.dark,
  };

  var OT_ESTADO_COLORS = {
    CREADA: BOOTSTRAP.secondary,
    ASIGNADA: BOOTSTRAP.warning,
    EN_EJECUCION: BOOTSTRAP.primary,
    REASIGNADA: BOOTSTRAP.info,
    MANTENIMIENTO: BOOTSTRAP.info,
    REALIZADA: BOOTSTRAP.success,
    REALIZADA_PENDIENTE_COMPROBACION: BOOTSTRAP.info,
    PENDIENTE_VALIDACION: BOOTSTRAP.warning,
    VALIDADA: BOOTSTRAP.success,
    OBSERVADA: BOOTSTRAP.danger,
    FINALIZADA: BOOTSTRAP.success,
    CANCELADA: BOOTSTRAP.danger,
  };

  function isDark() {
    return document.documentElement.getAttribute('data-bs-theme') === 'dark';
  }

  function chartDefaults() {
    var dark = isDark();
    return {
      color: dark ? '#e2e8f0' : '#334155',
      borderColor: dark ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.08)',
      legendColor: dark ? '#cbd5e1' : '#475569',
    };
  }

  function colorFor(map, key, fallback) {
    if (map && Object.prototype.hasOwnProperty.call(map, key)) {
      return map[key];
    }
    return fallback || BOOTSTRAP.secondary;
  }

  global.DelcoCharts = {
    BOOTSTRAP: BOOTSTRAP,
    ESTADO_SYNC_COLORS: ESTADO_SYNC_COLORS,
    ESTADO_REVISION_COLORS: ESTADO_REVISION_COLORS,
    MOV_TIPO_COLORS: MOV_TIPO_COLORS,
    OT_ESTADO_COLORS: OT_ESTADO_COLORS,
    isDark: isDark,
    chartDefaults: chartDefaults,
    colorFor: colorFor,
  };
})(typeof window !== 'undefined' ? window : this);
