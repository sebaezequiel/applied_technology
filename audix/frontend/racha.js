// Lógica de racha: días con escucha, racha actual y estado de la mascota.
// Sin dependencias, así puede probarse con `node --test` y usarse en el navegador.

const Racha = (() => {
  const CLAVE = "audix-escuchas";

  function iso(fecha) {
    const anio = fecha.getFullYear();
    const mes = String(fecha.getMonth() + 1).padStart(2, "0");
    const dia = String(fecha.getDate()).padStart(2, "0");
    return `${anio}-${mes}-${dia}`;
  }

  function sumarDias(fecha, cantidad) {
    const resultado = new Date(fecha);
    resultado.setDate(resultado.getDate() + cantidad);
    return resultado;
  }

  // Días seguidos hasta hoy. Si hoy todavía no escuchaste, cuenta desde ayer.
  function calcularRacha(fechas, hoy = new Date()) {
    const conjunto = new Set(fechas);
    let cursor = conjunto.has(iso(hoy)) ? hoy : sumarDias(hoy, -1);
    let racha = 0;
    while (conjunto.has(iso(cursor))) {
      racha += 1;
      cursor = sumarDias(cursor, -1);
    }
    return racha;
  }

  // Lunes a domingo de la semana actual: true si hubo escucha ese día.
  function diasDeLaSemana(fechas, hoy = new Date()) {
    const conjunto = new Set(fechas);
    const lunes = sumarDias(hoy, -((hoy.getDay() + 6) % 7));
    return [0, 1, 2, 3, 4, 5, 6].map((desplazamiento) =>
      conjunto.has(iso(sumarDias(lunes, desplazamiento)))
    );
  }

  // Estado visual de la mascota según la racha.
  function estadoMascota(fechas, hoy = new Date()) {
    const racha = calcularRacha(fechas, hoy);
    if (racha >= 7) return "celebrando";
    if (racha >= 3) return "auriculares";
    const conjunto = new Set(fechas);
    if (conjunto.has(iso(hoy)) || conjunto.has(iso(sumarDias(hoy, -1)))) {
      return "despertandose";
    }
    return "dormido";
  }

  function registrarEscucha(fechas, hoy = new Date()) {
    const dia = iso(hoy);
    return fechas.includes(dia) ? fechas : [...fechas, dia];
  }

  function cargar(almacen = globalThis.localStorage) {
    try {
      return JSON.parse(almacen.getItem(CLAVE)) || [];
    } catch {
      return [];
    }
  }

  function guardar(fechas, almacen = globalThis.localStorage) {
    almacen.setItem(CLAVE, JSON.stringify(fechas));
  }

  return {
    iso,
    calcularRacha,
    diasDeLaSemana,
    estadoMascota,
    registrarEscucha,
    cargar,
    guardar,
  };
})();

if (typeof module !== "undefined" && module.exports) {
  module.exports = Racha;
} else {
  window.Racha = Racha;
}
