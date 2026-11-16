// Acceso con clave. La sesión viaja en una cookie que este código no puede
// leer (HttpOnly): acá solo se pregunta al servidor si está activa.
//
// Todos los pedidos a la API pasan por Sesion.pedir. Si alguno vuelve con 401
// (sesión vencida o cerrada desde otro lado), aparece la pantalla de acceso.

const Sesion = (() => {
  const API = AUDIX_API;
  const $ = (id) => document.getElementById(id);
  let enviando = false;

  function mostrarAcceso({ configurada = true } = {}) {
    const pantalla = $("acceso");
    if (!pantalla.hidden) return;
    // Lo que estuviera sonando se corta: la app queda tapada hasta entrar.
    if ("speechSynthesis" in window) speechSynthesis.cancel();
    $("acceso-sin-clave").hidden = configurada;
    $("form-acceso").hidden = !configurada;
    $("acceso-error").hidden = true;
    pantalla.hidden = false;
    if (configurada) $("input-clave").focus();
  }

  async function pedir(url, opciones) {
    const respuesta = await fetch(url, opciones);
    if (respuesta.status === 401) mostrarAcceso();
    return respuesta;
  }

  function mostrarError(texto) {
    $("acceso-error").textContent = texto;
    $("acceso-error").hidden = false;
  }

  async function entrar(evento) {
    evento.preventDefault();
    if (enviando) return;
    const clave = $("input-clave").value;
    if (!clave) return;

    enviando = true;
    $("btn-entrar").disabled = true;
    try {
      const respuesta = await fetch(`${API}/sesion`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clave }),
      });
      if (respuesta.ok) {
        // Se recarga para que la app arranque limpia, ya con la sesión.
        location.reload();
        return;
      }
      const datos = await respuesta.json().catch(() => ({}));
      mostrarError(typeof datos.detail === "string" ? datos.detail : "No se pudo entrar.");
      $("input-clave").select();
    } catch {
      mostrarError("No se pudo conectar con la PC. Revisá que esté encendida.");
    } finally {
      enviando = false;
      $("btn-entrar").disabled = false;
    }
  }

  async function salir() {
    try {
      await fetch(`${API}/sesion`, { method: "DELETE" });
    } catch {
      // Sin conexión no se puede cerrar en el servidor; igual se recarga.
    }
    location.reload();
  }

  async function comprobar() {
    try {
      const respuesta = await fetch(`${API}/sesion`);
      if (!respuesta.ok) return;
      const estado = await respuesta.json();
      if (!estado.activa) mostrarAcceso({ configurada: estado.configurada });
    } catch {
      // Sin conexión: la app muestra sus propios avisos.
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("form-acceso").addEventListener("submit", entrar);
    $("btn-salir").addEventListener("click", salir);
    comprobar();
  });

  return { pedir };
})();
