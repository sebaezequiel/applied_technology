// Audix: lógica de la pantalla de inicio.
// Pendiente: reproductor de capítulos (Web Speech API) y racha real.

const DIAS = ["L", "M", "X", "J", "V", "S", "D"];

function renderSemana(diasEscuchados = []) {
  const contenedor = document.getElementById("semana");
  contenedor.innerHTML = "";
  DIAS.forEach((letra, indice) => {
    const dia = document.createElement("div");
    dia.className = "dia" + (diasEscuchados.includes(indice) ? " escuchado" : "");
    dia.innerHTML = `<span></span>${letra}`;
    contenedor.appendChild(dia);
  });
}

function iniciar() {
  renderSemana([]);

  document.getElementById("btn-escuchar").addEventListener("click", () => {
    // TODO: abrir lista de libros y reproductor
  });

  const inputArchivo = document.getElementById("input-archivo");
  document.getElementById("btn-importar").addEventListener("click", () => {
    inputArchivo.click();
  });
  inputArchivo.addEventListener("change", () => {
    // TODO: enviar el archivo a la API (POST /libros)
  });
}

document.addEventListener("DOMContentLoaded", iniciar);
