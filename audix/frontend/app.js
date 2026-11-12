// Audix: navegación entre pantallas, biblioteca, racha y lector.

const API = AUDIX_API;
const DIAS = ["L", "M", "X", "J", "V", "S", "D"];

const pantallas = ["inicio", "biblioteca", "libro", "lector"];

function mostrar(id) {
  pantallas.forEach((nombre) => {
    document.getElementById(nombre).hidden = nombre !== id;
  });
  window.scrollTo(0, 0);
}

// ---------- Inicio: mascota y racha ----------

function renderInicio() {
  const fechas = Racha.cargar();
  const hoy = new Date();
  const racha = Racha.calcularRacha(fechas, hoy);
  const estado = Racha.estadoMascota(fechas, hoy);

  document.getElementById("mascota").innerHTML = Mascota.svg(estado);
  document.getElementById("racha-titulo").textContent =
    `Racha: ${racha} ${racha === 1 ? "día" : "días"}`;
  document.getElementById("racha-detalle").textContent =
    racha === 0 ? "Escuchá hoy para empezar tu racha" : "¡Seguí así!";

  const semana = document.getElementById("semana");
  semana.innerHTML = "";
  Racha.diasDeLaSemana(fechas, hoy).forEach((escuchado, indice) => {
    const dia = document.createElement("div");
    dia.className = "dia" + (escuchado ? " escuchado" : "");
    dia.innerHTML = `<span></span>${DIAS[indice]}`;
    semana.appendChild(dia);
  });
}

// ---------- Biblioteca y libro ----------

async function renderBiblioteca() {
  const lista = document.getElementById("lista-libros");
  const aviso = document.getElementById("aviso-biblioteca");
  lista.innerHTML = "";
  aviso.textContent = "Cargando biblioteca…";

  try {
    const respuesta = await fetch(`${API}/libros`);
    const libros = await respuesta.json();
    aviso.textContent = libros.length ? "" : "Todavía no hay libros. Procesá un EPUB con el script.";

    libros.forEach((libro) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "item-libro";
      item.innerHTML = `<strong></strong><span></span>`;
      item.querySelector("strong").textContent = libro.titulo;
      item.querySelector("span").textContent =
        `${libro.autor || "Autor desconocido"} · ${libro.capitulos} capítulos`;
      item.addEventListener("click", () => abrirLibro(libro.id));
      lista.appendChild(item);
    });
  } catch {
    aviso.textContent = "No hay conexión con la API. ¿Está corriendo uvicorn?";
  }
}

let libroActual = null;

async function abrirLibro(libroId) {
  const respuesta = await fetch(`${API}/libros/${libroId}`);
  libroActual = await respuesta.json();

  document.getElementById("titulo-libro").textContent = libroActual.titulo;
  document.getElementById("autor-libro").textContent = libroActual.autor || "";

  const lista = document.getElementById("lista-capitulos");
  lista.innerHTML = "";
  libroActual.capitulos.forEach((capitulo) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "item-capitulo";
    item.textContent = `${capitulo.numero}. ${capitulo.titulo}`;
    item.addEventListener("click", () => leerCapitulo(capitulo.numero));
    lista.appendChild(item);
  });

  mostrar("libro");
}

// ---------- Importar EPUB ----------

async function importarEpub(archivo) {
  const aviso = document.getElementById("aviso-importar");
  const boton = document.getElementById("btn-importar");
  aviso.textContent = `Procesando "${archivo.name}"… puede tardar unos segundos.`;
  boton.disabled = true;

  const formulario = new FormData();
  formulario.append("archivo", archivo);

  try {
    const respuesta = await fetch(`${API}/libros`, { method: "POST", body: formulario });
    const datos = await respuesta.json().catch(() => ({}));

    if (!respuesta.ok) {
      aviso.textContent = datos.detail || "No se pudo importar el libro.";
      return;
    }

    aviso.textContent = `Listo: ${datos.titulo} (${datos.capitulos} capítulos).`;
    mostrar("biblioteca");
    renderBiblioteca();
  } catch {
    aviso.textContent = "No hay conexión con la API. ¿Está corriendo uvicorn?";
  } finally {
    boton.disabled = false;
  }
}

// ---------- Lector ----------

async function leerCapitulo(numero) {
  mostrar("lector");
  document.getElementById("titulo-lector").textContent = libroActual.titulo;
  await Lector.abrir(libroActual.id, libroActual.capitulos.length, numero);
}

function renderLector(estado) {
  const capitulo = libroActual?.capitulos.find((c) => c.numero === estado.numero);
  document.getElementById("capitulo-actual").textContent =
    capitulo ? `${capitulo.numero}. ${capitulo.titulo}` : "";
  document.getElementById("progreso-lector").textContent =
    `Capítulo ${estado.numero} de ${estado.total} · ${Lector.progreso()}%`;
  document.getElementById("barra-progreso").style.width = `${Lector.progreso()}%`;

  const boton = document.getElementById("btn-reproducir");
  boton.textContent = estado.reproduciendo ? "❚❚ Pausa" : "▶ Reproducir";
}

function cargarVoces() {
  const selector = document.getElementById("selector-voz");
  const voces = Lector.vocesEspanol();
  selector.innerHTML = "";

  if (voces.length === 0) {
    selector.innerHTML = `<option>Voz predeterminada</option>`;
    return;
  }
  voces.forEach((voz, indice) => {
    const opcion = document.createElement("option");
    opcion.value = indice;
    opcion.textContent = `${voz.name} (${voz.lang})`;
    selector.appendChild(opcion);
  });
  Lector.setVoz(voces[0]);
}

// ---------- Eventos ----------

function conectarEventos() {
  document.getElementById("btn-escuchar").addEventListener("click", () => {
    mostrar("biblioteca");
    renderBiblioteca();
  });

  const inputArchivo = document.getElementById("input-archivo");
  document.getElementById("btn-importar").addEventListener("click", () => {
    inputArchivo.click();
  });
  inputArchivo.addEventListener("change", () => {
    const archivo = inputArchivo.files[0];
    inputArchivo.value = "";
    if (archivo) importarEpub(archivo);
  });

  document.querySelectorAll("[data-volver]").forEach((boton) => {
    boton.addEventListener("click", () => {
      const destino = boton.dataset.volver;
      if (destino === "inicio") renderInicio();
      mostrar(destino);
    });
  });

  document.getElementById("btn-reproducir").addEventListener("click", () => {
    if (Lector.estado.reproduciendo) Lector.pausar();
    else Lector.play();
  });
  document.getElementById("btn-anterior").addEventListener("click", () => Lector.anterior());
  document.getElementById("btn-siguiente").addEventListener("click", () => Lector.siguiente());

  document.getElementById("selector-velocidad").addEventListener("change", (evento) => {
    Lector.setVelocidad(Number(evento.target.value));
  });
  document.getElementById("selector-voz").addEventListener("change", (evento) => {
    const voces = Lector.vocesEspanol();
    Lector.setVoz(voces[Number(evento.target.value)]);
  });

  Lector.onEscuchar(() => {
    Racha.guardar(Racha.registrarEscucha(Racha.cargar()));
  });
  Lector.onCambio(renderLector);

  speechSynthesis.addEventListener("voiceschanged", cargarVoces);
}

function iniciar() {
  renderInicio();
  mostrar("inicio");
  cargarVoces();
  conectarEventos();
}

document.addEventListener("DOMContentLoaded", iniciar);
