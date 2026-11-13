// Audix: navegación entre pantallas, biblioteca, racha y lector.

const API = AUDIX_API;
const DIAS = ["L", "M", "X", "J", "V", "S", "D"];

const pantallas = ["inicio", "biblioteca", "libro", "lector"];

function mostrar(id) {
  pantallas.forEach((nombre) => {
    document.getElementById(nombre).hidden = nombre !== id;
  });
  window.scrollTo(0, 0);
  actualizarMini();
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

// Cambia el título guardado (por ejemplo, si la importación lo leyó mal).
async function renombrarLibroActual() {
  const nuevoTitulo = prompt("Nuevo título del libro:", libroActual.titulo);
  if (nuevoTitulo === null) return; // canceló
  if (!nuevoTitulo.trim()) {
    mostrarAvisoLibro("El título no puede estar vacío.");
    return;
  }
  try {
    const respuesta = await fetch(`${API}/libros/${libroActual.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: nuevoTitulo }),
    });
    if (!respuesta.ok) {
      mostrarAvisoLibro(await mensajeDeError(respuesta));
      return;
    }
    const datos = await respuesta.json();
    libroActual.titulo = datos.titulo;
    pintarLibro();
    mostrarAvisoLibro("Título actualizado.");
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

// ---------- Modal de importación ----------

let _archivoPdfSeleccionado = null;

function abrirModal() {
  document.getElementById("modal-importar").hidden = false;
  mostrarPaso("paso-tipo-archivo");
}

function cerrarModal() {
  document.getElementById("modal-importar").hidden = true;
  _archivoPdfSeleccionado = null;
  // Limpiar avisos
  ["aviso-epub", "aviso-pdf-tipo", "aviso-preview"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.textContent = "";
  });
  ["progreso-importar", "progreso-pdf"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) { el.hidden = true; el.value = 0; }
  });
  document.getElementById("btn-elegir-epub").disabled = false;
  document.getElementById("btn-elegir-pdf").disabled = false;
  document.getElementById("btn-preview-confirmar").disabled = false;
}

function mostrarPaso(id) {
  ["paso-tipo-archivo", "paso-epub", "paso-pdf-tipo", "paso-preview"].forEach((paso) => {
    document.getElementById(paso).hidden = paso !== id;
  });
}

// --- EPUB ---

function importarEpub(archivo) {
  const aviso = document.getElementById("aviso-epub");
  const boton = document.getElementById("btn-elegir-epub");
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

  pedido.upload.onload = () => {
    progreso.removeAttribute("value");
    aviso.textContent = "Procesando el EPUB… puede tardar unos segundos.";
  };

  const terminar = () => {
    boton.disabled = false;
    progreso.hidden = true;
    progreso.value = 0;
  };

  pedido.onload = () => {
    terminar();
    let datos = {};
    try { datos = JSON.parse(pedido.responseText); } catch { /**/ }
    if (pedido.status >= 200 && pedido.status < 300) {
      cerrarModal();
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

// --- PDF: vista previa ---

async function cargarPreviewPdf(archivo, tipo) {
  const aviso = document.getElementById("aviso-pdf-tipo");
  const btnElegir = document.getElementById("btn-elegir-pdf");
  btnElegir.disabled = true;
  aviso.textContent = "Analizando el PDF…";

  try {
    const formulario = new FormData();
    formulario.append("archivo", archivo);
    const respuesta = await fetch(`${API}/libros/pdf/preview?tipo=${tipo}`, {
      method: "POST",
      body: formulario,
    });
    const datos = await respuesta.json();
    if (!respuesta.ok) {
      aviso.textContent = mensajeDetalle(respuesta.status, datos);
      btnElegir.disabled = false;
      return;
    }
    aviso.textContent = "";
    btnElegir.disabled = false;
    mostrarPreview(datos, archivo, tipo);
  } catch {
    aviso.textContent = mensajeConexion();
    btnElegir.disabled = false;
  }
}

function mostrarPreview(datos, archivo, tipo) {
  const lista = document.getElementById("lista-preview");
  const desc = document.getElementById("preview-desc");
  lista.innerHTML = "";

  const n = datos.capitulos.length;
  desc.textContent = `Se detectaron ${n} ${n === 1 ? "capítulo" : "capítulos"} en "${archivo.name}" (tipo: ${tipo}).`;

  datos.capitulos.forEach((cap) => {
    const li = document.createElement("li");
    const chars = cap.caracteres >= 1000
      ? `${Math.round(cap.caracteres / 1000)} k`
      : `${cap.caracteres}`;
    li.innerHTML = `<span>${cap.numero}. ${cap.titulo}</span><span class="preview-num">${chars} chars</span>`;
    lista.appendChild(li);
  });

  mostrarPaso("paso-preview");

  // Guardar para usar al confirmar
  document.getElementById("btn-preview-confirmar").onclick = () => confirmarImportarPdf(archivo, tipo);
  document.getElementById("btn-preview-volver").onclick = () => mostrarPaso("paso-pdf-tipo");
}

// --- PDF: importar definitivo ---

function confirmarImportarPdf(archivo, tipo) {
  const aviso = document.getElementById("aviso-preview");
  const boton = document.getElementById("btn-preview-confirmar");
  const progreso = document.getElementById("progreso-pdf");

  boton.disabled = true;
  progreso.hidden = false;
  progreso.value = 0;
  aviso.textContent = `Importando "${archivo.name}"…`;

  const formulario = new FormData();
  formulario.append("archivo", archivo);
  const pedido = new XMLHttpRequest();
  pedido.open("POST", `${API}/libros/pdf?tipo=${tipo}`);

  pedido.upload.onprogress = (evento) => {
    if (!evento.lengthComputable) return;
    const porcentaje = Math.round((evento.loaded / evento.total) * 100);
    progreso.value = porcentaje;
    aviso.textContent = `Subiendo "${archivo.name}"… ${porcentaje}%`;
  };

  pedido.upload.onload = () => {
    progreso.removeAttribute("value");
    aviso.textContent = "Procesando el PDF…";
  };

  const terminar = () => {
    boton.disabled = false;
    progreso.hidden = true;
    progreso.value = 0;
  };

  pedido.onload = () => {
    terminar();
    let datos = {};
    try { datos = JSON.parse(pedido.responseText); } catch { /**/ }
    if (pedido.status >= 200 && pedido.status < 300) {
      cerrarModal();
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
  document
    .getElementById("portada-lector")
    .replaceChildren(crearPortada(libroActual.portada, libroActual.titulo, "portada-lector-img"));
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
  actualizarMini();
}

// ---------- Mini reproductor (se ve al salir del lector mientras suena) ----------

function actualizarMini() {
  const barra = document.getElementById("mini-reproductor");
  const enLector = !document.getElementById("lector").hidden;
  const sonando = Lector.estado.reproduciendo && libroActual;
  barra.hidden = !(sonando && !enLector);
  if (barra.hidden) return;

  const capitulo = libroActual.capitulos.find((c) => c.numero === Lector.estado.numero);
  document
    .getElementById("mini-portada")
    .replaceChildren(crearPortada(libroActual.portada, libroActual.titulo, "portada-mini"));
  document.getElementById("mini-titulo").textContent = libroActual.titulo;
  document.getElementById("mini-capitulo").textContent =
    capitulo ? `${capitulo.numero}. ${capitulo.titulo}` : "";
  document.getElementById("mini-play").textContent = Lector.estado.reproduciendo ? "❚❚" : "▶";
}

function conectarMini() {
  document.getElementById("mini-info").addEventListener("click", () => mostrar("lector"));
  document.getElementById("mini-play").addEventListener("click", () => {
    if (Lector.estado.reproduciendo) Lector.pausar();
    else Lector.play();
  });
}

function cargarVoces() {
  const selector = document.getElementById("selector-voz");
  const voces = Lector.vocesDisponibles();
  selector.innerHTML = "";

  if (voces.length === 0) {
    selector.innerHTML = `<option>Voz predeterminada</option>`;
    return;
  }

  const guardada = Lector.vozGuardada();
  voces.forEach((voz) => {
    const opcion = document.createElement("option");
    opcion.value = voz.name;
    opcion.textContent = `${voz.name} (${voz.lang})`;
    if (voz.name === guardada) opcion.selected = true;
    selector.appendChild(opcion);
  });

  const elegida = voces.find((voz) => voz.name === selector.value) || voces[0];
  Lector.setVoz(elegida);
}

// ---------- Eventos ----------

function conectarEventos() {
  document.getElementById("btn-escuchar").addEventListener("click", () => {
    mostrar("biblioteca");
    renderBiblioteca();
  });

  // Botón principal: abre el modal
  document.getElementById("btn-importar").addEventListener("click", abrirModal);

  // Paso 1: elegir tipo de archivo
  document.getElementById("opcion-epub").addEventListener("click", () => mostrarPaso("paso-epub"));
  document.getElementById("opcion-pdf").addEventListener("click", () => mostrarPaso("paso-pdf-tipo"));

  // Cancelar desde cualquier paso
  ["modal-cerrar-1", "modal-cerrar-epub", "modal-cerrar-pdf-tipo", "modal-cerrar-preview"].forEach((id) => {
    document.getElementById(id).addEventListener("click", cerrarModal);
  });

  // Cerrar al hacer click fuera del modal
  document.getElementById("modal-importar").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) cerrarModal();
  });

  // Paso 2a: EPUB
  const inputEpub = document.getElementById("input-epub");
  document.getElementById("btn-elegir-epub").addEventListener("click", () => inputEpub.click());
  inputEpub.addEventListener("change", () => {
    const archivo = inputEpub.files[0];
    inputEpub.value = "";
    if (archivo) importarEpub(archivo);
  });

  // Paso 2b: PDF → al elegir archivo, pasa a la vista previa
  const inputPdf = document.getElementById("input-pdf");
  document.getElementById("btn-elegir-pdf").addEventListener("click", () => inputPdf.click());
  inputPdf.addEventListener("change", () => {
    const archivo = inputPdf.files[0];
    inputPdf.value = "";
    if (!archivo) return;
    _archivoPdfSeleccionado = archivo;
    const tipo = document.querySelector('input[name="tipo-pdf"]:checked')?.value || "novela";
    cargarPreviewPdf(archivo, tipo);
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

  document.getElementById("btn-cambiar-titulo").addEventListener("click", renombrarLibroActual);
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
    const voz = Lector.vocesDisponibles().find((v) => v.name === evento.target.value);
    if (voz) Lector.setVoz(voz);
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
  conectarMini();
}

document.addEventListener("DOMContentLoaded", iniciar);
