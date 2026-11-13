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

// ---------- Mensajes de error ----------

function mensajeConexion() {
  return `No se pudo conectar con Audix en ${API}. ¿Está corriendo iniciar-audix.bat en la PC y estás en la misma Wi-Fi?`;
}

function mensajeDetalle(estado, datos) {
  if (datos && typeof datos.detail === "string") return datos.detail;
  return `Audix respondió con un error (${estado}).`;
}

async function mensajeDeError(respuesta) {
  const datos = await respuesta.json().catch(() => ({}));
  return mensajeDetalle(respuesta.status, datos);
}

// ---------- Portadas ----------

// Muestra la portada del libro, o la inicial del título si no hay o no carga.
function crearPortada(url, titulo, clase) {
  const contenedor = document.createElement("div");
  contenedor.className = clase;
  const inicial = (titulo || "?").trim().charAt(0).toUpperCase();

  const mostrarInicial = () => {
    contenedor.innerHTML = "";
    contenedor.classList.add("sin-portada");
    contenedor.textContent = inicial;
  };

  if (!url) {
    mostrarInicial();
    return contenedor;
  }
  const imagen = document.createElement("img");
  imagen.alt = "";
  imagen.loading = "lazy";
  imagen.src = `${API}${url}`;
  imagen.onerror = mostrarInicial;
  contenedor.appendChild(imagen);
  return contenedor;
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
    if (!respuesta.ok) throw new Error(await mensajeDeError(respuesta));
    const libros = await respuesta.json();
    aviso.textContent = libros.length ? "" : "Todavía no hay libros. Importá un EPUB desde Inicio.";

    libros.forEach((libro) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "item-libro fila-libro";

      const texto = document.createElement("div");
      texto.className = "texto-libro";
      const titulo = document.createElement("strong");
      titulo.textContent = libro.titulo;
      const detalle = document.createElement("span");
      detalle.textContent = `${libro.autor || "Autor desconocido"} · ${libro.capitulos} capítulos`;
      texto.append(titulo, detalle);

      item.append(crearPortada(libro.portada, libro.titulo, "portada-mini"), texto);
      item.addEventListener("click", () => abrirLibro(libro.id));
      lista.appendChild(item);
    });
  } catch (error) {
    aviso.textContent = error instanceof TypeError ? mensajeConexion() : error.message;
  }
}

let libroActual = null;

function mostrarAvisoLibro(texto) {
  document.getElementById("aviso-libro").textContent = texto;
}

// Pinta la pantalla del libro con los datos que tiene libroActual.
function pintarLibro() {
  const libro = libroActual;
  document.getElementById("titulo-libro").textContent = libro.titulo;
  document.getElementById("autor-libro").textContent = libro.autor || "";

  document
    .getElementById("portada-libro")
    .replaceChildren(crearPortada(libro.portada, libro.titulo, "portada-grande"));

  const lista = document.getElementById("lista-capitulos");
  lista.innerHTML = "";
  libro.capitulos.forEach((capitulo) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "item-capitulo";
    item.textContent = `${capitulo.numero}. ${capitulo.titulo}`;
    item.addEventListener("click", () => leerCapitulo(capitulo.numero));
    lista.appendChild(item);
  });
}

async function abrirLibro(libroId) {
  try {
    const respuesta = await fetch(`${API}/libros/${libroId}`);
    if (!respuesta.ok) throw new Error(await mensajeDeError(respuesta));
    libroActual = await respuesta.json();
  } catch (error) {
    mostrar("biblioteca");
    document.getElementById("aviso-biblioteca").textContent =
      error instanceof TypeError ? mensajeConexion() : error.message;
    return;
  }
  mostrarAvisoLibro("");
  pintarLibro();
  mostrar("libro");
}

async function cambiarPortada(archivo) {
  mostrarAvisoLibro("Subiendo portada…");
  const formulario = new FormData();
  formulario.append("archivo", archivo);

  try {
    const respuesta = await fetch(`${API}/libros/${libroActual.id}/portada`, {
      method: "PUT",
      body: formulario,
    });
    if (!respuesta.ok) {
      mostrarAvisoLibro(await mensajeDeError(respuesta));
      return;
    }
    const datos = await respuesta.json();
    // El parámetro evita que el navegador muestre la portada vieja de caché.
    libroActual.portada = `${datos.portada}?v=${Date.now()}`;
    pintarLibro();
    mostrarAvisoLibro("Portada actualizada.");
  } catch {
    mostrarAvisoLibro(mensajeConexion());
  }
}

async function borrarLibroActual() {
  const titulo = libroActual.titulo;
  if (!confirm(`¿Borrar "${titulo}"? Se elimina de la PC y no se puede deshacer.`)) return;

  try {
    const respuesta = await fetch(`${API}/libros/${libroActual.id}`, { method: "DELETE" });
    if (!respuesta.ok) {
      mostrarAvisoLibro(await mensajeDeError(respuesta));
      return;
    }
    libroActual = null;
    mostrar("biblioteca");
    renderBiblioteca();
  } catch {
    mostrarAvisoLibro(mensajeConexion());
  }
}

// ---------- Importar EPUB ----------

// Usa XMLHttpRequest porque fetch no informa el avance de la subida.
function importarEpub(archivo) {
  const aviso = document.getElementById("aviso-importar");
  const boton = document.getElementById("btn-importar");
  const progreso = document.getElementById("progreso-importar");

  boton.disabled = true;
  progreso.hidden = false;
  progreso.value = 0;
  aviso.textContent = `Subiendo "${archivo.name}"…`;

  const formulario = new FormData();
  formulario.append("archivo", archivo);
  const pedido = new XMLHttpRequest();
  pedido.open("POST", `${API}/libros`);

  pedido.upload.onprogress = (evento) => {
    if (!evento.lengthComputable) return;
    const porcentaje = Math.round((evento.loaded / evento.total) * 100);
    progreso.value = porcentaje;
    aviso.textContent = `Subiendo "${archivo.name}"… ${porcentaje}%`;
  };

  // Subido el archivo, la PC lo procesa: la barra pasa a modo indefinido.
  pedido.upload.onload = () => {
    progreso.removeAttribute("value");
    aviso.textContent = "Procesando el EPUB en la PC… puede tardar unos segundos.";
  };

  const terminar = () => {
    boton.disabled = false;
    progreso.hidden = true;
  };

  pedido.onload = () => {
    terminar();
    let datos = {};
    try {
      datos = JSON.parse(pedido.responseText);
    } catch {
      // respuesta sin JSON: se usa el mensaje genérico
    }
    if (pedido.status >= 200 && pedido.status < 300) {
      aviso.textContent = `Listo: ${datos.titulo} (${datos.capitulos} capítulos).`;
      mostrar("biblioteca");
      renderBiblioteca();
    } else {
      aviso.textContent = mensajeDetalle(pedido.status, datos);
    }
  };

  pedido.onerror = () => {
    terminar();
    aviso.textContent = mensajeConexion();
  };

  pedido.send(formulario);
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

  const inputPortada = document.getElementById("input-portada");
  document.getElementById("btn-cambiar-portada").addEventListener("click", () => {
    inputPortada.click();
  });
  inputPortada.addEventListener("change", () => {
    const archivo = inputPortada.files[0];
    inputPortada.value = "";
    if (archivo) cambiarPortada(archivo);
  });

  document.getElementById("btn-borrar-libro").addEventListener("click", borrarLibroActual);

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
