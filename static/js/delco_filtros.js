/* Filtro de tres controles, el mismo de Tareas MoreApp.
   Cada .delco-filtro-builder[data-filtro-auto] arma sus tipos desde los paneles. */
(function () {
  function diaISO(fecha) {
    var m = String(fecha.getMonth() + 1).padStart(2, "0");
    var d = String(fecha.getDate()).padStart(2, "0");
    return fecha.getFullYear() + "-" + m + "-" + d;
  }

  function rangoFechas(clave) {
    var hoy = new Date();
    var hasta = diaISO(hoy);
    var desde = new Date(hoy.getFullYear(), hoy.getMonth(), hoy.getDate());
    if (clave === "mes") {
      desde = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
    } else {
      desde.setDate(desde.getDate() - (Number(clave) || 7) + 1);
    }
    return { desde: diaISO(desde), hasta: hasta };
  }

  function init(root) {
    var tipo = root.querySelector(".js-filtro-tipo");
    var btn = root.querySelector(".js-filtro-agregar");
    var rango = root.querySelector(".js-filtro-rango");
    var label = root.querySelector(".js-filtro-valor-label");
    var vacio = root.querySelector(".js-filtro-vacio");
    if (!tipo || !btn) return;

    root.querySelectorAll("[data-filtro-panel]").forEach(function (panel) {
      if (tipo.querySelector('option[value="' + panel.getAttribute("data-filtro-panel") + '"]')) return;
      var opt = document.createElement("option");
      opt.value = panel.getAttribute("data-filtro-panel");
      opt.textContent = panel.getAttribute("data-filtro-titulo") || opt.value;
      tipo.appendChild(opt);
    });

    function panelActual() {
      return root.querySelector('[data-filtro-panel="' + tipo.value + '"]');
    }

    function mostrar() {
      var clave = tipo.value;
      root.querySelectorAll("[data-filtro-panel]").forEach(function (el) {
        el.classList.toggle("d-none", el.getAttribute("data-filtro-panel") !== clave);
      });
      if (vacio) vacio.classList.toggle("d-none", !!clave);
      var modo = panelActual() && panelActual().getAttribute("data-filtro-modo");
      if (rango) rango.classList.toggle("d-none", modo !== "fecha");
      if (label) label.textContent = modo === "fecha" ? "Desde" : "Qué buscar";
    }

    tipo.addEventListener("change", mostrar);
    mostrar();

    root.querySelectorAll("[data-filtro-panel] input").forEach(function (input) {
      input.addEventListener("keydown", function (ev) {
        if (ev.key === "Enter") {
          ev.preventDefault();
          btn.click();
        }
      });
    });

    var carga = null;

    function limpiar() {
      var box = panelActual();
      if (!box) return;
      box.querySelectorAll("input, select, textarea").forEach(function (el) {
        if (el.type === "hidden") return;
        el.value = "";
      });
      var hasta = root.querySelector(".js-filtro-hasta");
      if (hasta) hasta.value = "";
    }

    function aplicar(url, opts) {
      opts = opts || {};
      var destino = new URL(url, window.location.href);
      if (root.getAttribute("data-navegacion") === "pagina" || destino.pathname !== window.location.pathname) {
        window.location.assign(destino.href);
        return;
      }
      var listaId = root.getAttribute("data-lista");
      var lista = listaId ? document.getElementById(listaId) : null;
      var chips = root.querySelector(".js-filtro-activos");
      if (!lista) {
        window.location.assign(destino.href);
        return;
      }
      if (carga && carga.abort) {
        try { carga.abort(); } catch (e) { /* ignore */ }
      }
      carga = new AbortController();
      var token = carga;
      lista.classList.add("is-loading");
      btn.disabled = true;
      fetch(destino.href, {
        credentials: "same-origin",
        signal: token.signal,
        headers: { "X-Requested-With": "XMLHttpRequest", Accept: "text/html" }
      })
        .then(function (resp) { return resp.text(); })
        .then(function (html) {
          var doc = new DOMParser().parseFromString(html, "text/html");
          var nextLista = doc.getElementById(listaId);
          if (!nextLista) throw new Error("sin listado");
          lista.innerHTML = nextLista.innerHTML;
          var nextRoot = doc.querySelector(".delco-filtro-builder[data-filtro-auto]");
          var nextChips = nextRoot && nextRoot.querySelector(".js-filtro-activos");
          if (chips && nextChips) chips.innerHTML = nextChips.innerHTML;
          (root.getAttribute("data-sync") || "").split(/\s+/).forEach(function (id) {
            if (!id) return;
            var actual = document.getElementById(id);
            var nuevo = doc.getElementById(id);
            if (actual && nuevo) actual.innerHTML = nuevo.innerHTML;
          });
          if (opts.history !== "none") {
            window.history.pushState({ delcoFiltro: 1 }, "", destino.pathname + destino.search);
          }
          if (opts.limpiar) limpiar();
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") return;
          if (typeof window.showToast === "function") {
            window.showToast("No se pudo actualizar el listado.", "danger");
          }
        })
        .then(function () {
          if (carga !== token) return;
          lista.classList.remove("is-loading");
          btn.disabled = false;
        });
    }

    btn.addEventListener("click", function () {
      var box = panelActual();
      if (!box) return;
      var params = new URLSearchParams(window.location.search);
      params.delete("page");
      var modo = box.getAttribute("data-filtro-modo") || "valor";
      if (modo === "fecha") {
        var desdeEl = box.querySelector("input");
        var hastaEl = root.querySelector(".js-filtro-hasta");
        var desde = desdeEl ? desdeEl.value : "";
        var hasta = hastaEl ? hastaEl.value : "";
        if (!desde && !hasta) return;
        var nombreDesde = box.getAttribute("data-filtro-desde") || "fecha_desde";
        var nombreHasta = box.getAttribute("data-filtro-hasta") || "fecha_hasta";
        if (desde) params.set(nombreDesde, desde); else params.delete(nombreDesde);
        if (hasta) params.set(nombreHasta, hasta); else params.delete(nombreHasta);
      } else if (modo === "rango") {
        var sel = box.querySelector("select");
        if (!sel || !sel.value) return;
        var fechas = rangoFechas(sel.value);
        params.set(box.getAttribute("data-filtro-desde") || "fecha_desde", fechas.desde);
        params.set(box.getAttribute("data-filtro-hasta") || "fecha_hasta", fechas.hasta);
      } else if (modo === "grupo") {
        var textoGrupo = box.querySelector("input[data-filtro-param], textarea[data-filtro-param]");
        if (textoGrupo && !String(textoGrupo.value || "").trim()) return;
        var alguno = false;
        box.querySelectorAll("[data-filtro-param]").forEach(function (el) {
          var valor = String(el.value || "").trim();
          if (!valor) {
            params.delete(el.getAttribute("data-filtro-param"));
            return;
          }
          alguno = true;
          params.set(el.getAttribute("data-filtro-param"), valor);
        });
        if (!alguno) return;
      } else {
        var input = box.querySelector("[data-filtro-valor]") || box.querySelector("select, input, textarea");
        var valor = input ? String(input.value || "").trim() : "";
        if (!valor) return;
        params.set(box.getAttribute("data-filtro-param") || tipo.value, valor);
      }
      (box.getAttribute("data-filtro-borra") || "").split(",").forEach(function (clave) {
        if (clave) params.delete(clave);
      });
      var texto = params.toString();
      aplicar(window.location.pathname + (texto ? "?" + texto : ""), { limpiar: true });
    });

    document.addEventListener("click", function (ev) {
      var link = ev.target && ev.target.closest ? ev.target.closest("a[data-delco-partial]") : null;
      if (!link) return;
      var listaId = root.getAttribute("data-lista");
      var lista = listaId ? document.getElementById(listaId) : null;
      if (!root.contains(link) && !(lista && lista.contains(link))) return;
      if (root.getAttribute("data-navegacion") === "pagina") return;
      if (ev.button !== 0 || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      aplicar(link.href, { history: "push" });
    });
  }

  function boot() {
    document.querySelectorAll(".delco-filtro-builder[data-filtro-auto]").forEach(function (root) {
      if (root.getAttribute("data-filtro-listo") === "1") return;
      root.setAttribute("data-filtro-listo", "1");
      init(root);
    });
  }

  boot();
  window.addEventListener("delco:page-ready", boot);
})();
