// Pruebas de la lógica de racha. Ejecutar con: node --test tests/
const test = require("node:test");
const assert = require("node:assert/strict");

const Racha = require("../frontend/racha.js");

const hoy = new Date(2026, 10, 11); // 11 de noviembre de 2026 (hora local)

test("racha cuenta días seguidos hasta hoy", () => {
  const fechas = ["2026-11-09", "2026-11-10", "2026-11-11"];
  assert.equal(Racha.calcularRacha(fechas, hoy), 3);
});

test("si hoy todavía no escuchaste, la racha cuenta desde ayer", () => {
  const fechas = ["2026-11-08", "2026-11-09", "2026-11-10"];
  assert.equal(Racha.calcularRacha(fechas, hoy), 3);
});

test("un día sin escuchar corta la racha", () => {
  const fechas = ["2026-11-07", "2026-11-09", "2026-11-10", "2026-11-11"];
  assert.equal(Racha.calcularRacha(fechas, hoy), 3);
});

test("sin escuchas la racha es cero", () => {
  assert.equal(Racha.calcularRacha([], hoy), 0);
});

test("registrarEscucha no duplica el mismo día", () => {
  const fechas = Racha.registrarEscucha(["2026-11-11"], hoy);
  assert.deepEqual(fechas, ["2026-11-11"]);
});

test("registrarEscucha agrega el día de hoy", () => {
  const fechas = Racha.registrarEscucha(["2026-11-10"], hoy);
  assert.deepEqual(fechas, ["2026-11-10", "2026-11-11"]);
});

test("diasDeLaSemana empieza en lunes", () => {
  // 11 de noviembre de 2026 es miércoles: la semana va del lunes 9 al domingo 15.
  const semana = Racha.diasDeLaSemana(["2026-11-09", "2026-11-11"], hoy);
  assert.deepEqual(semana, [true, false, true, false, false, false, false]);
});

test("estado dormido sin escuchas recientes", () => {
  assert.equal(Racha.estadoMascota(["2026-11-01"], hoy), "dormido");
});

test("estado despertándose si escuchaste hoy o ayer", () => {
  assert.equal(Racha.estadoMascota(["2026-11-10"], hoy), "despertandose");
});

test("estado con auriculares con 3 días seguidos", () => {
  const fechas = ["2026-11-09", "2026-11-10", "2026-11-11"];
  assert.equal(Racha.estadoMascota(fechas, hoy), "auriculares");
});

test("estado celebrando con 7 días seguidos o más", () => {
  const fechas = [
    "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08",
    "2026-11-09", "2026-11-10", "2026-11-11",
  ];
  assert.equal(Racha.estadoMascota(fechas, hoy), "celebrando");
});
