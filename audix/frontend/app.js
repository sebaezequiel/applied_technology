// Audix: navegación entre pantallas, biblioteca, racha y lector.

const API = AUDIX_API;
const DIAS = ["L", "M", "X", "J", "V", "S", "D"];
const NOMBRES_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"];
const VELOCIDADES = [0.8, 1, 1.25, 1.5, 2];
const CLAVE_ULTIMO = "audix-ultimo";
const LIBROS_PARA_BUSCADOR = 6;

const pantallas = ["inicio", "biblioteca", "libro", "lector"];
let pantallaActual = "inicio";

let libroActual = null;   // el libro abierto en la pantalla "libro"
let libroSonando = null;  // el libro cargado en el lector (puede ser otro)
let librosCache = null;   // última lista de la biblioteca, para pintar sin esperar
let catalogoVoces = null; // voces y tonos para la narración con IA (GET /voces)
let formatoImportacion = null;   // "epub" | "pdf", elegido en el paso 1 del modal de importar
let libroParaCambiarVoz = null;  // libro sobre el que actúa la hoja "Cambiar voz"

const $ = (id) => document.getElementById(id);

function icono(nombre) {
  return `<svg class="icono" aria-hidden="true"><use href="#i-${nombre}"/></svg>`;
}

// ---------- Navegación ----------
// Cada pantalla es una entrada del historial, así el botón "atrás" del celular
// vuelve a la pantalla anterior en vez de cerrar la app. Las hojas (modales)
// también suman una entrada: "atrás" las cierra.

function refrescar(id) {
  if (id === "inicio") renderInicio();
  if (id === "biblioteca") {
    renderBiblioteca();
    cargarImportaciones();
  }
  if (id === "libro") pintarLibro();
  if (id === "lector") pintarLector();
  actualizarMini();
}

function mostrar(id) {
  pantallaActual = id;
  pantallas.forEach((nombre) => {
    $(nombre).hidden = nombre !== id;
  });
  // Reinicia la animación de entrada.
  const pantalla = $(id);
  pantalla.classList.remove("entrando");
  void pantalla.offsetWidth;
  pantalla.classList.add("entrando");
  window.scrollTo(0, 0);
  refrescar(id);
}

function navegar(id) {
  const enHoja = Boolean(history.state && history.state.hoja);
  ocultarHoja();
  if (id === pantallaActual) {
    if (enHoja) history.back();
    refrescar(id);
    return;
  }
  // Si había una hoja abierta, la pantalla nueva ocupa su lugar en el historial.
  if (enHoja) history.replaceState({ pantalla: id }, "");
  else history.pushState({ pantalla: id }, "");
  mostrar(id);
}

function volver() {
  if (pantallaActual === "inicio") return;
  history.back();
}

function alCambiarHistorial(evento) {
  let id = (evento.state && evento.state.pantalla) || "inicio";
  // Pantallas que necesitan un libro: si ya no está, se cae a la anterior con sentido.
  if (id === "libro" && !libroActual) id = "biblioteca";
  if (id === "lector" && !libroSonando) id = libroActual ? "libro" : "biblioteca";
  if (!evento.state || evento.state.pantalla !== id || evento.state.hoja) {
    history.replaceState({ pantalla: id }, "");
  }
  const habiaHoja = Boolean(hojaAbierta);
  ocultarHoja();
  if (id === pantallaActual) {
    if (!habiaHoja) refrescar(id);
    return;
  }
  mostrar(id);
}

// ---------- Hojas (modales que suben desde abajo) ----------

let hojaAbierta = null;
let focoAnterior = null;

function abrirHoja(id) {
  if (hojaAbierta) {
    // Cambia de hoja sin sumar otra entrada al historial.
    $(hojaAbierta).hidden = true;
  } else {
    focoAnterior = document.activeElement;
    history.pushState({ pantalla: pantallaActual, hoja: true }, "");
  }
  hojaAbierta = id;
  $(id).hidden = false;
  document.body.classList.add("sin-scroll");
  const foco = $(id).querySelector("[data-foco], .hoja button, .hoja input");
  if (foco) foco.focus({ preventScroll: true });
}

// Solo saca la hoja de la pantalla; no toca el historial.
function ocultarHoja() {
  if (!hojaAbierta) return;
  $(hojaAbierta).hidden = true;
  hojaAbierta = null;
  document.body.classList.remove("sin-scroll");
  limpiarImportacion();
  if (focoAnterior && document.contains(focoAnterior)) focoAnterior.focus({ preventScroll: true });
  focoAnterior = null;
}

function cerrarHoja() {
  if (!hojaAbierta) return;
  if (history.state && history.state.hoja) history.back();
  else ocultarHoja();
}

// ---------- Avisos breves ----------

let _timerToast = null;

function toast(texto) {
  const caja = $("toast");
  caja.textContent = texto;
  caja.hidden = false;
  caja.classList.remove("entrando");
  void caja.offsetWidth;
  caja.classList.add("entrando");
  clearTimeout(_timerToast);
  _timerToast = setTimeout(() => {
    caja.hidden = true;
  }, 3200);
}

// ---------- Mensajes de error ----------

function mensajeConexion() {
  return "No se pudo conectar con Audix. ¿Está corriendo iniciar-audix.bat en la PC y estás en la misma Wi-Fi?";
}

function mensajeDetalle(estado, datos) {
  if (datos && typeof datos.detail === "string") return datos.detail;
  return `Audix respondió con un error (${estado}).`;
}

async function mensajeDeError(respuesta) {
  const datos = await respuesta.json().catch(() => ({}));
  return mensajeDetalle(respuesta.status, datos);
}

function textoDeError(error) {
  return error instanceof TypeError ? mensajeConexion() : error.message;
}

// ---------- Portadas ----------

// Muestra la portada del libro, o la inicial del título si no hay o no carga.
function crearPortada(url, titulo, clase) {
  const contenedor = document.createElement("div");
  contenedor.className = `portada ${clase}`;
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
  imagen.decoding = "async";
  imagen.src = `${API}${url}`;
  imagen.onerror = mostrarInicial;
  contenedor.appendChild(imagen);
  return contenedor;
}

// ---------- Progreso guardado ----------

function leerUltimo() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE_ULTIMO)) || null;
  } catch {
    return null;
  }
}

function guardarUltimo(libro) {
  localStorage.setItem(
    CLAVE_ULTIMO,
    JSON.stringify({
      id: libro.id,
      titulo: libro.titulo,
      autor: libro.autor || "",
      portada: libro.portada,
      total: libro.capitulos.length,
    })
  );
}

// Avance aproximado de un libro (0 a 1) según el capítulo en el que quedaste.
function avanceDelLibro(libroId, totalCapitulos) {
  const progreso = Lector.leerProgreso(libroId);
  if (!progreso || !totalCapitulos) return null;
  let dentroDelCapitulo = 0;
  if (Lector.estado.libroId === libroId && Lector.estado.numero === progreso.numero) {
    dentroDelCapitulo = Lector.progreso() / 100;
  }
  const fraccion = (progreso.numero - 1 + dentroDelCapitulo) / totalCapitulos;
  return { numero: progreso.numero, fraccion: Math.max(0, Math.min(fraccion, 1)) };
}

// ---------- Inicio: mascota, racha y seguir escuchando ----------

function saludo(hora) {
  if (hora < 6) return "Buenas noches";
  if (hora < 13) return "Buen día";
  if (hora < 20) return "Buenas tardes";
  return "Buenas noches";
}

function renderInicio() {
  const fechas = Racha.cargar();
  const hoy = new Date();
  const racha = Racha.calcularRacha(fechas, hoy);
  const estado = Racha.estadoMascota(fechas, hoy);
  const escuchoHoy = fechas.includes(Racha.iso(hoy));

  $("saludo").textContent = saludo(hoy.getHours());
  $("mascota").innerHTML = Mascota.svg(estado);
  $("racha-numero").textContent = racha;
  $("racha-unidad").textContent = racha === 1 ? "día" : "días";

  let detalle = "Escuchá hoy para empezar tu racha.";
  if (racha > 0 && !escuchoHoy) detalle = "Escuchá hoy para no perderla.";
  else if (racha >= 7) detalle = "Una semana o más seguida. ¡Imparable!";
  else if (racha > 0) detalle = "Hoy ya escuchaste. ¡Seguí así!";
  $("racha-detalle").textContent = detalle;

  const semana = $("semana");
  const indiceHoy = (hoy.getDay() + 6) % 7;
  semana.innerHTML = "";
  Racha.diasDeLaSemana(fechas, hoy).forEach((escuchado, indice) => {
    const dia = document.createElement("div");
    dia.className = "dia" + (escuchado ? " escuchado" : "") + (indice === indiceHoy ? " hoy" : "");
    dia.setAttribute(
      "aria-label",
      `${NOMBRES_DIAS[indice]}: ${escuchado ? "escuchaste" : "sin escuchar"}`
    );
    dia.innerHTML = `<span>${escuchado ? icono("check") : ""}</span>${DIAS[indice]}`;
    semana.appendChild(dia);
  });

  renderSeguir();
}

function renderSeguir() {
  const ultimo = leerUltimo();
  const seccion = $("seguir");
  // Si el mini reproductor ya muestra un libro, la tarjeta sería repetir lo mismo.
  const miniVisible = Boolean(libroSonando) && Lector.estado.libroId === libroSonando.id;
  seccion.hidden = !ultimo || miniVisible;
  if (seccion.hidden) return;

  const avance = avanceDelLibro(ultimo.id, ultimo.total);
  $("seguir-portada").replaceChildren(crearPortada(ultimo.portada, ultimo.titulo, "portada-mini"));
  $("seguir-titulo").textContent = ultimo.titulo;
  $("seguir-detalle").textContent = avance
    ? `Capítulo ${avance.numero} de ${ultimo.total}`
    : `${ultimo.total} capítulos`;
  $("seguir-barra").style.width = `${Math.round((avance ? avance.fraccion : 0) * 100)}%`;
}

async function seguirEscuchando() {
  const ultimo = leerUltimo();
  if (!ultimo) return;
  // Si ese libro ya está cargado en el lector, se abre sin volver a pedirlo.
  if (libroSonando && libroSonando.id === ultimo.id && Lector.estado.trozos.length) {
    navegar("lector");
    Lector.play();
    return;
  }
  const libro = await pedirLibro(ultimo.id);
  if (!libro) return;
  libroActual = libro;
  const progreso = Lector.leerProgreso(libro.id);
  leerCapitulo(numeroParaContinuar(libro, progreso), { reproducir: true });
}

// ---------- Biblioteca ----------

function pintarEsqueletos() {
  const lista = $("lista-libros");
  lista.innerHTML = "";
  for (let i = 0; i < 3; i += 1) {
    const fila = document.createElement("div");
    fila.className = "item-libro esqueleto";
    fila.innerHTML = '<span class="portada portada-mini"></span><span class="esqueleto-lineas"><i></i><i></i></span>';
    lista.appendChild(fila);
  }
}

function pintarEstado(lista, { estado, titulo, texto, boton, accion }) {
  const caja = document.createElement("div");
  caja.className = "estado-vacio";
  caja.innerHTML = `<div class="estado-mascota">${Mascota.svg(estado)}</div>`;
  const h = document.createElement("h2");
  h.textContent = titulo;
  const p = document.createElement("p");
  p.textContent = texto;
  caja.append(h, p);
  if (boton) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "boton-secundario";
    b.textContent = boton;
    b.addEventListener("click", accion);
    caja.appendChild(b);
  }
  lista.replaceChildren(caja);
}

function pintarBiblioteca() {
  const lista = $("lista-libros");
  const libros = librosCache || [];
  const buscador = $("buscador");
  buscador.hidden = libros.length < LIBROS_PARA_BUSCADOR;
  const consulta = buscador.hidden ? "" : $("input-buscar").value.trim().toLowerCase();

  if (libros.length === 0) {
    pintarEstado(lista, {
      estado: "dormido",
      titulo: "Tu biblioteca está vacía",
      texto: "Importá un EPUB o un PDF y empezá a escuchar.",
      boton: "Importar libro",
      accion: abrirImportacion,
    });
    return;
  }

  const visibles = libros.filter((libro) =>
    `${libro.titulo} ${libro.autor || ""}`.toLowerCase().includes(consulta)
  );
  lista.innerHTML = "";
  if (visibles.length === 0) {
    const nada = document.createElement("p");
    nada.className = "aviso centrado";
    nada.textContent = "Ningún libro coincide con la búsqueda.";
    lista.appendChild(nada);
    return;
  }

  visibles.forEach((libro) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "item-libro";

    const texto = document.createElement("span");
    texto.className = "texto-libro";
    const titulo = document.createElement("strong");
    titulo.textContent = libro.titulo;
    const autor = document.createElement("span");
    autor.className = "detalle";
    autor.textContent = libro.autor || "Autor desconocido";
    texto.append(titulo, autor);

    const avance = avanceDelLibro(libro.id, libro.capitulos);
    const estado = document.createElement("span");
    estado.className = "detalle";
    if (avance) {
      estado.textContent =
        `Capítulo ${avance.numero} de ${libro.capitulos}` + sufijoDeAudio(libro.audio);
      const barra = document.createElement("span");
      barra.className = "barra-fina";
      barra.appendChild(document.createElement("span")).style.width = `${Math.round(avance.fraccion * 100)}%`;
      texto.append(estado, barra);
    } else {
      estado.textContent =
        `${libro.capitulos} ${libro.capitulos === 1 ? "capítulo" : "capítulos"} · Sin empezar` +
        sufijoDeAudio(libro.audio);
      texto.append(estado);
    }

    const flecha = document.createElement("span");
    flecha.className = "flecha";
    flecha.innerHTML = icono("chevron");

    item.append(crearPortada(libro.portada, libro.titulo, "portada-lista"), texto, flecha);
    item.addEventListener("click", () => abrirLibro(libro.id));
    lista.appendChild(item);
  });
}

function sufijoDeAudio(audio) {
  const texto = textoDeAudio(audio);
  return texto ? ` · ${texto}` : "";
}

async function renderBiblioteca() {
  // Con lista previa se pinta al instante y se actualiza por detrás.
  if (librosCache) pintarBiblioteca();
  else pintarEsqueletos();

  try {
    const respuesta = await Sesion.pedir(`${API}/libros`);
    if (!respuesta.ok) throw new Error(await mensajeDeError(respuesta));
    librosCache = await respuesta.json();
    pintarBiblioteca();
    vigilarAudio();
  } catch (error) {
    if (librosCache) {
      toast(textoDeError(error));
      return;
    }
    $("buscador").hidden = true;
    pintarEstado($("lista-libros"), {
      estado: "dormido",
      titulo: "No se pudo cargar la biblioteca",
      texto: textoDeError(error),
      boton: "Reintentar",
      accion: renderBiblioteca,
    });
  }
}

// ---------- Libro ----------

async function pedirLibro(libroId) {
  try {
    const respuesta = await Sesion.pedir(`${API}/libros/${libroId}`);
    if (!respuesta.ok) throw new Error(await mensajeDeError(respuesta));
    return await respuesta.json();
  } catch (error) {
    toast(textoDeError(error));
    return null;
  }
}

function numeroParaContinuar(libro, progreso) {
  const numeros = libro.capitulos.map((c) => c.numero);
  if (progreso && numeros.includes(progreso.numero)) return progreso.numero;
  return numeros[0];
}

// Pinta la pantalla del libro con los datos que tiene libroActual.
function pintarLibro() {
  const libro = libroActual;
  if (!libro) return;
  const total = libro.capitulos.length;
  const progreso = Lector.leerProgreso(libro.id);

  $("titulo-libro").textContent = libro.titulo;
  $("autor-libro").textContent = libro.autor || "Autor desconocido";
  $("meta-libro").textContent =
    `${total} ${total === 1 ? "capítulo" : "capítulos"}` + sufijoDeAudio(libro.audio);
  $("portada-libro").replaceChildren(crearPortada(libro.portada, libro.titulo, "portada-grande"));
  reintentarAudioSiHaceFalta(libro);
  vigilarAudio();

  const continuar = $("btn-continuar-libro");
  continuar.disabled = total === 0;
  $("texto-continuar-libro").textContent = progreso
    ? `Continuar · Capítulo ${numeroParaContinuar(libro, progreso)}`
    : "Empezar a escuchar";

  const lista = $("lista-capitulos");
  lista.innerHTML = "";
  libro.capitulos.forEach((capitulo) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "item-capitulo";
    item.dataset.numero = capitulo.numero;

    const numero = document.createElement("span");
    numero.className = "cap-numero";
    numero.textContent = capitulo.numero;
    const titulo = document.createElement("span");
    titulo.className = "cap-titulo";
    titulo.textContent = capitulo.titulo;
    const estado = document.createElement("span");
    estado.className = "cap-estado";

    item.append(numero, titulo, estado);
    item.addEventListener("click", () => leerCapitulo(capitulo.numero, { reproducir: true }));
    lista.appendChild(item);
  });
  marcarCapitulos();
}

// Marca en la lista los capítulos ya escuchados y el que está en curso.
function marcarCapitulos() {
  if (!libroActual) return;
  const progreso = Lector.leerProgreso(libroActual.id);
  const sonandoEste =
    Lector.estado.libroId === libroActual.id && Lector.estado.reproduciendo;

  document.querySelectorAll("#lista-capitulos .item-capitulo").forEach((item) => {
    const numero = Number(item.dataset.numero);
    const actual = Boolean(progreso) && numero === progreso.numero;
    const escuchado = Boolean(progreso) && numero < progreso.numero;
    item.classList.toggle("actual", actual);
    item.classList.toggle("escuchado", escuchado);
    const estado = item.querySelector(".cap-estado");
    let marca = "";
    if (actual) marca = sonandoEste ? "sonando" : "en-curso";
    else if (escuchado) marca = "escuchado";
    if (estado.dataset.marca === marca) return;
    estado.dataset.marca = marca;
    if (marca === "sonando") estado.innerHTML = '<span class="ondas"><i></i><i></i><i></i></span>';
    else if (marca === "en-curso") estado.textContent = "En curso";
    else if (marca === "escuchado") estado.innerHTML = icono("check");
    else estado.textContent = "";
    if (actual) item.setAttribute("aria-current", "true");
    else item.removeAttribute("aria-current");
  });
}

async function abrirLibro(libroId) {
  const libro = await pedirLibro(libroId);
  if (!libro) return;
  libroActual = libro;
  navegar("libro");
}

async function cambiarPortada(archivo) {
  toast("Subiendo portada…");
  const formulario = new FormData();
  formulario.append("archivo", archivo);

  try {
    const respuesta = await Sesion.pedir(`${API}/libros/${libroActual.id}/portada`, {
      method: "PUT",
      body: formulario,
    });
    if (!respuesta.ok) {
      toast(await mensajeDeError(respuesta));
      return;
    }
    const datos = await respuesta.json();
    // El parámetro evita que el navegador muestre la portada vieja de caché.
    libroActual.portada = `${datos.portada}?v=${Date.now()}`;
    sincronizarLibro(libroActual);
    pintarLibro();
    toast("Portada actualizada.");
  } catch {
    toast(mensajeConexion());
  }
}

// Lleva los cambios de título o portada a la lista, al lector y a "seguir escuchando".
function sincronizarLibro(libro) {
  if (librosCache) {
    const enLista = librosCache.find((l) => l.id === libro.id);
    if (enLista) {
      enLista.titulo = libro.titulo;
      enLista.portada = libro.portada;
    }
  }
  if (libroSonando && libroSonando.id === libro.id) {
    libroSonando.titulo = libro.titulo;
    libroSonando.portada = libro.portada;
    $("mini-reproductor").dataset.libro = "";
  }
  const ultimo = leerUltimo();
  if (ultimo && ultimo.id === libro.id) guardarUltimo(libro);
  actualizarMini();
}

function abrirCambioDeTitulo() {
  const input = $("input-titulo");
  input.value = libroActual.titulo;
  $("aviso-titulo").textContent = "";
  abrirHoja("hoja-titulo");
  input.focus();
  input.select();
}

// Cambia el título guardado (por ejemplo, si la importación lo leyó mal).
async function guardarTitulo(evento) {
  evento.preventDefault();
  const aviso = $("aviso-titulo");
  const boton = $("btn-guardar-titulo");
  const nuevoTitulo = $("input-titulo").value.trim();
  if (!nuevoTitulo) {
    aviso.textContent = "El título no puede estar vacío.";
    return;
  }
  if (nuevoTitulo === libroActual.titulo) {
    cerrarHoja();
    return;
  }
  boton.disabled = true;
  try {
    const respuesta = await Sesion.pedir(`${API}/libros/${libroActual.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ titulo: nuevoTitulo }),
    });
    if (!respuesta.ok) {
      aviso.textContent = await mensajeDeError(respuesta);
      return;
    }
    const datos = await respuesta.json();
    libroActual.titulo = datos.titulo;
    sincronizarLibro(libroActual);
    pintarLibro();
    cerrarHoja();
    toast("Título actualizado.");
  } catch {
    aviso.textContent = mensajeConexion();
  } finally {
    boton.disabled = false;
  }
}

function abrirConfirmacionDeBorrado() {
  $("borrar-desc").textContent =
    `"${libroActual.titulo}" se elimina de la PC junto con tu avance. No se puede deshacer.`;
  $("aviso-borrar").textContent = "";
  abrirHoja("hoja-borrar");
}

async function borrarLibroActual() {
  const aviso = $("aviso-borrar");
  const boton = $("btn-confirmar-borrar");
  const id = libroActual.id;
  boton.disabled = true;
  try {
    const respuesta = await Sesion.pedir(`${API}/libros/${id}`, { method: "DELETE" });
    if (!respuesta.ok) {
      aviso.textContent = await mensajeDeError(respuesta);
      return;
    }
  } catch {
    aviso.textContent = mensajeConexion();
    return;
  } finally {
    boton.disabled = false;
  }

  if (Lector.estado.libroId === id) Lector.cerrar();
  if (libroSonando && libroSonando.id === id) libroSonando = null;
  Lector.borrarProgreso(id);
  const ultimo = leerUltimo();
  if (ultimo && ultimo.id === id) localStorage.removeItem(CLAVE_ULTIMO);
  if (librosCache) librosCache = librosCache.filter((libro) => libro.id !== id);
  libroActual = null;

  // Vuelve dos pasos: cierra la hoja y sale de la pantalla del libro borrado.
  ocultarHoja();
  history.go(-2);
  toast("Libro borrado.");
}

// ---------- Voz: voz del sistema o narración con IA ----------

// Catálogo de voces y tonos para la narración (se usa en el modal de
// importar y en la hoja "Cambiar voz"). Se pide una sola vez.
async function cargarCatalogoVoces() {
  if (catalogoVoces) return catalogoVoces;
  try {
    const respuesta = await Sesion.pedir(`${API}/voces`);
    if (respuesta.ok) catalogoVoces = await respuesta.json();
  } catch {
    // Sin conexión: se vuelve a intentar la próxima vez que haga falta.
  }
  return catalogoVoces;
}

function pintarSelectoresDeVoz(selectorVoz, selectorTono) {
  if (!catalogoVoces) return;
  // Las voces se agrupan por idioma (Español, Inglés), en el orden en que llegan.
  selectorVoz.innerHTML = "";
  const grupos = new Map();
  catalogoVoces.voces.forEach((voz) => {
    const idioma = voz.idioma || "Otros";
    if (!grupos.has(idioma)) grupos.set(idioma, document.createElement("optgroup"));
    const opcion = document.createElement("option");
    opcion.value = voz.id;
    opcion.textContent = voz.nombre;
    grupos.get(idioma).appendChild(opcion);
  });
  grupos.forEach((grupo, idioma) => {
    grupo.label = idioma;
    selectorVoz.appendChild(grupo);
  });
  selectorTono.innerHTML = "";
  catalogoVoces.tonos.forEach((tono) => {
    const opcion = document.createElement("option");
    opcion.value = tono.id;
    opcion.textContent = tono.nombre;
    selectorTono.appendChild(opcion);
  });
}

function nombreDeVoz(id) {
  const voz = catalogoVoces && catalogoVoces.voces.find((v) => v.id === id);
  return (voz && voz.nombre) || "Voz narrada";
}

function nombreDeTono(id) {
  const tono = catalogoVoces && catalogoVoces.tonos.find((t) => t.id === id);
  return (tono && tono.nombre) || "Normal";
}

// Lee la voz y el tono elegidos en el paso "Elegí la voz" del modal de importar.
// Todos los libros se importan con narración; la voz del sistema queda de respaldo.
function configDeVozImportar() {
  return {
    motor: "narracion",
    voz_id: $("selector-voz-importar").value,
    tono: $("selector-tono-importar").value || "normal",
  };
}

function parametrosDeVoz(config) {
  return new URLSearchParams({ motor_voz: config.motor, voz_id: config.voz_id || "", tono: config.tono });
}

// ---------- Hoja "Cambiar voz" (libros ya importados) ----------

function abrirCambioDeVoz(libro) {
  libroParaCambiarVoz = libro;
  const config = libro.voz || { motor: "sistema", voz_id: null, tono: "normal" };
  const sinAudio = config.motor !== "narracion";
  $("desc-voz").textContent = sinAudio
    ? "Este libro todavía se lee con la voz del sistema. Elegí una voz y Audix genera su audio en segundo plano."
    : "Si cambiás la voz o el tono, el audio se vuelve a generar en segundo plano.";
  $("btn-guardar-voz").textContent = sinAudio ? "Generar audio" : "Guardar";
  $("aviso-voz").textContent = "";
  cargarCatalogoVoces().then(() => {
    if (!catalogoVoces) {
      $("aviso-voz").textContent =
        "No se pudieron cargar las voces. Reiniciá el servidor de Audix y volvé a intentar.";
      return;
    }
    pintarSelectoresDeVoz($("selector-voz-editar"), $("selector-tono-editar"));
    $("selector-voz-editar").value = config.voz_id || catalogoVoces.voz_predeterminada;
    $("selector-tono-editar").value = config.tono || "normal";
  });
  abrirHoja("hoja-voz");
}

async function guardarVoz() {
  const aviso = $("aviso-voz");
  const boton = $("btn-guardar-voz");
  const libro = libroParaCambiarVoz;
  if (!$("selector-voz-editar").value) {
    aviso.textContent = "No hay voces para elegir. Reiniciá el servidor de Audix y volvé a intentar.";
    return;
  }
  const cuerpo = {
    motor: "narracion",
    voz_id: $("selector-voz-editar").value,
    tono: $("selector-tono-editar").value,
  };

  boton.disabled = true;
  try {
    const respuesta = await Sesion.pedir(`${API}/libros/${libro.id}/voz`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cuerpo),
    });
    if (!respuesta.ok) {
      aviso.textContent = await mensajeDeError(respuesta);
      return;
    }
    const datos = await respuesta.json();
    sincronizarVozLibro(libro.id, datos);
    cerrarHoja();
    toast("Generando el audio en segundo plano.");
  } catch {
    aviso.textContent = mensajeConexion();
  } finally {
    boton.disabled = false;
  }
}

// Lleva el cambio de voz (y el estado del audio) a todas las vistas que puedan tener una copia del libro.
function sincronizarVozLibro(libroId, datos) {
  const { voz, audio } = datos;
  if (libroActual && libroActual.id === libroId) {
    libroActual.voz = voz;
    libroActual.audio = audio;
    pintarLibro();
  }
  if (librosCache) {
    const enLista = librosCache.find((l) => l.id === libroId);
    if (enLista) {
      enLista.voz = voz;
      enLista.audio = audio;
    }
  }
  if (libroSonando && libroSonando.id === libroId) {
    libroSonando.voz = voz;
    libroSonando.audio = audio;
    // La voz cambió: hay que volver a abrir el capítulo para que tome la nueva.
    Lector.cerrar();
    pintarAjustesDeVoz();
    renderLector(Lector.estado);
    actualizarMini();
  }
  vigilarAudio();
}

// ---------- Audio del libro (se genera en segundo plano al importar) ----------

function textoDeAudio(audio) {
  if (!audio) return "";
  if (audio.error && !audio.generando) return "Audio pausado por un error";
  if (audio.listos >= audio.total) return "Audio listo";
  return `Generando audio ${audio.listos}/${audio.total}`;
}

let _timerAudio = null;
const _reintentosDeAudioPedidos = new Set();

// Mientras algún libro está generando su audio, actualiza el avance cada pocos
// segundos (solo en la biblioteca y en la pantalla del libro).
function vigilarAudio() {
  clearTimeout(_timerAudio);
  const generando =
    (librosCache || []).some((l) => l.audio && l.audio.generando) ||
    Boolean(libroActual && libroActual.audio && libroActual.audio.generando);
  if (!generando) return;
  _timerAudio = setTimeout(async () => {
    try {
      if (pantallaActual === "biblioteca") {
        const respuesta = await Sesion.pedir(`${API}/libros`);
        if (respuesta.ok) {
          librosCache = await respuesta.json();
          pintarBiblioteca();
        }
      } else if (pantallaActual === "libro" && libroActual) {
        const respuesta = await Sesion.pedir(`${API}/libros/${libroActual.id}`);
        if (respuesta.ok) {
          const datos = await respuesta.json();
          libroActual.audio = datos.audio;
          pintarLibro();
        }
      } else {
        return; // en otras pantallas no hace falta; se retoma al volver
      }
    } catch {
      // Sin conexión: se reintenta en el próximo ciclo.
    }
    vigilarAudio();
  }, 5000);
}

// Si el audio se frenó por un error (por ejemplo, la PC estuvo sin internet),
// al abrir el libro se pide retomarlo, una vez por sesión.
function reintentarAudioSiHaceFalta(libro) {
  const audio = libro.audio;
  if (!audio || !audio.error || audio.generando || _reintentosDeAudioPedidos.has(libro.id)) return;
  _reintentosDeAudioPedidos.add(libro.id);
  Sesion.pedir(`${API}/libros/${libro.id}/audio`, { method: "POST" })
    .then((respuesta) => (respuesta.ok ? respuesta.json() : null))
    .then((estado) => {
      if (!estado || !libroActual || libroActual.id !== libro.id) return;
      libroActual.audio = {
        listos: estado.listos.length,
        total: estado.total,
        generando: estado.generando,
        error: estado.error,
      };
      pintarLibro();
    })
    .catch(() => {});
}

// ---------- Importación ----------

function abrirImportacion() {
  mostrarPaso("paso-tipo-archivo");
  abrirHoja("modal-importar");
}

function limpiarImportacion() {
  ["aviso-epub", "aviso-pdf-tipo"].forEach((id) => {
    $(id).textContent = "";
  });
  const progreso = $("progreso-importar");
  progreso.hidden = true;
  progreso.value = 0;
  $("btn-elegir-epub").disabled = false;
  $("btn-elegir-pdf").disabled = false;
  $("aviso-voces").textContent = "";
}

function mostrarPaso(id) {
  ["paso-tipo-archivo", "paso-voz", "paso-epub", "paso-pdf-tipo"].forEach((paso) => {
    $(paso).hidden = paso !== id;
  });
}

// Paso "¿Cómo querés escucharlo?": común a EPUB y PDF.
function abrirPasoVoz(formato) {
  formatoImportacion = formato;
  mostrarPaso("paso-voz");
  cargarVocesParaImportar();
}

// Pinta los selectores de la importación. Si el catálogo no llega (por
// ejemplo, el servidor no se reinició después de actualizar), avisa en vez
// de dejar los selectores vacíos.
function cargarVocesParaImportar() {
  $("aviso-voces").textContent = "";
  return cargarCatalogoVoces().then(() => {
    if (!catalogoVoces) {
      $("aviso-voces").textContent =
        "No se pudieron cargar las voces. Reiniciá el servidor de Audix y volvé a intentar.";
      return;
    }
    pintarSelectoresDeVoz($("selector-voz-importar"), $("selector-tono-importar"));
  });
}

// --- EPUB ---

function importarEpub(archivo) {
  const aviso = $("aviso-epub");
  const boton = $("btn-elegir-epub");
  const progreso = $("progreso-importar");

  boton.disabled = true;
  progreso.hidden = false;
  progreso.value = 0;
  aviso.textContent = `Subiendo "${archivo.name}"…`;

  const formulario = new FormData();
  formulario.append("archivo", archivo);
  const parametros = parametrosDeVoz(configDeVozImportar());
  const pedido = new XMLHttpRequest();
  pedido.open("POST", `${API}/libros?${parametros}`);

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
      navegar("biblioteca");
      toast(`"${datos.titulo || archivo.name}" ya está en tu biblioteca.`);
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

// --- PDF: importación en segundo plano ---

function importarPdf(archivo, tipo) {
  const aviso = $("aviso-pdf-tipo");
  const boton = $("btn-elegir-pdf");
  boton.disabled = true;
  aviso.textContent = `Enviando "${archivo.name}"…`;

  const formulario = new FormData();
  formulario.append("archivo", archivo);
  const parametros = parametrosDeVoz(configDeVozImportar());
  parametros.set("tipo", tipo);
  Sesion.pedir(`${API}/libros/pdf?${parametros}`, { method: "POST", body: formulario })
    .then(async (respuesta) => {
      const datos = await respuesta.json().catch(() => ({}));
      if (!respuesta.ok) {
        aviso.textContent = mensajeDetalle(respuesta.status, datos);
        return;
      }
      navegar("biblioteca");
      toast("Importando en segundo plano. Podés seguir usando la app.");
    })
    .catch(() => {
      aviso.textContent = mensajeConexion();
    })
    .finally(() => {
      boton.disabled = false;
    });
}

let _timerImportaciones = null;
let _listosVistos = new Set();

async function cargarImportaciones() {
  clearTimeout(_timerImportaciones);
  let trabajos = [];
  try {
    const respuesta = await Sesion.pedir(`${API}/trabajos`);
    // Los trabajos "audio" son pedidos del lector, no importaciones.
    if (respuesta.ok) trabajos = (await respuesta.json()).filter((t) => t.tipo !== "audio");
  } catch {
    // Sin conexión: se reintenta en el próximo ciclo.
  }
  pintarImportaciones(trabajos);

  // Un libro nuevo terminó: refresca la biblioteca una sola vez por trabajo.
  const listos = trabajos.filter((t) => t.estado === "listo").map((t) => t.id);
  const hayNuevos = listos.some((id) => !_listosVistos.has(id));
  _listosVistos = new Set(listos);
  if (hayNuevos && pantallaActual === "biblioteca") renderBiblioteca();

  if (trabajos.some((t) => t.estado === "en_curso")) {
    _timerImportaciones = setTimeout(cargarImportaciones, 2000);
  }
}

async function quitarTrabajo(trabajoId) {
  try {
    await Sesion.pedir(`${API}/trabajos/${trabajoId}`, { method: "DELETE" });
  } catch {
    // Si falla, la fila sigue ahí y se puede volver a intentar.
  }
}

function pintarImportaciones(trabajos) {
  const seccion = $("importaciones");
  const lista = $("lista-importaciones");
  lista.innerHTML = "";
  seccion.hidden = trabajos.length === 0;

  trabajos.forEach((trabajo) => {
    const fila = document.createElement("div");
    fila.className = `fila-importacion ${trabajo.estado}`;

    const texto = document.createElement("div");
    texto.className = "texto-libro";
    const nombre = document.createElement("strong");
    nombre.textContent = trabajo.nombre;
    const detalle = document.createElement("span");
    detalle.className = "detalle";

    if (trabajo.estado === "en_curso") {
      detalle.textContent = `Procesando… ${trabajo.progreso}%`;
      const barra = document.createElement("span");
      barra.className = "barra-fina";
      barra.setAttribute("role", "progressbar");
      barra.setAttribute("aria-valuenow", trabajo.progreso);
      barra.appendChild(document.createElement("span")).style.width = `${Number(trabajo.progreso) || 0}%`;
      texto.append(nombre, detalle, barra);
    } else if (trabajo.estado === "listo") {
      detalle.textContent = "Listo para escuchar";
      texto.append(nombre, detalle);
    } else {
      detalle.textContent = `Error: ${trabajo.error}`;
      texto.append(nombre, detalle);
    }
    fila.appendChild(texto);

    const acciones = document.createElement("div");
    acciones.className = "acciones-importacion";
    if (trabajo.estado === "listo") {
      const abrir = document.createElement("button");
      abrir.type = "button";
      abrir.className = "boton-chico";
      abrir.textContent = "Abrir";
      abrir.addEventListener("click", async () => {
        await quitarTrabajo(trabajo.id);
        abrirLibro(trabajo.libro_id);
      });
      acciones.appendChild(abrir);
    }
    if (trabajo.estado !== "en_curso") {
      const quitar = document.createElement("button");
      quitar.type = "button";
      quitar.className = "boton-texto";
      quitar.textContent = "Quitar";
      quitar.addEventListener("click", async () => {
        await quitarTrabajo(trabajo.id);
        cargarImportaciones();
      });
      acciones.appendChild(quitar);
    }
    fila.appendChild(acciones);
    lista.appendChild(fila);
  });
}

// ---------- Lector ----------

async function leerCapitulo(numero, { reproducir = false } = {}) {
  libroSonando = libroActual;
  guardarUltimo(libroSonando);
  navegar("lector");
  try {
    const motor = libroSonando.voz ? libroSonando.voz.motor : "sistema";
    await Lector.abrir(libroSonando.id, libroSonando.capitulos.length, numero, motor);
    if (reproducir) Lector.play();
  } catch (error) {
    toast((error && error.message) || "No se pudo cargar el capítulo. Revisá la conexión con la PC.");
  }
}

// "Capítulo 2 · I": le da contexto a los títulos cortos fuera de la lista.
function etiquetaCapitulo(capitulo) {
  const titulo = capitulo.titulo || "";
  if (/^cap[ií]tulo\b/i.test(titulo)) return titulo;
  return `Capítulo ${capitulo.numero} · ${titulo}`;
}

function pintarLector() {
  if (!libroSonando) return;
  $("titulo-lector").textContent = libroSonando.titulo;
  $("portada-lector").replaceChildren(
    crearPortada(libroSonando.portada, libroSonando.titulo, "portada-lector-img")
  );
  pintarVelocidades();
  pintarAjustesDeVoz();
  renderLector(Lector.estado);
}

// Selector de voz del sistema: solo cuando suena la voz del sistema. Si el libro
// es narrado, un botón muestra la voz y el tono y permite cambiarlos.
function pintarAjustesDeVoz() {
  const esNarrado = Boolean(libroSonando && libroSonando.voz && libroSonando.voz.motor === "narracion");
  $("campo-voz-sistema").hidden = Lector.estado.motor !== "sistema";
  $("campo-voz-narracion").hidden = !esNarrado;
  if (esNarrado) {
    const { voz_id: vozId, tono } = libroSonando.voz;
    $("btn-cambiar-voz-lector").textContent = `${nombreDeVoz(vozId)} · ${nombreDeTono(tono)}`;
  }
}

// Icono del encabezado: qué voz suena y si se puede cambiar. Los avisos del
// cambio de voz se muestran como mensaje breve, una sola vez.
let ultimoAvisoDeVoz = "";
function pintarMotorDeVoz(estado) {
  const esNarrado = estado.motorDelLibro === "narracion";
  const boton = $("btn-motor-voz");
  const sistema = estado.motor === "sistema";
  boton.toggleAttribute("data-oculto", !esNarrado);
  boton.setAttribute("aria-pressed", String(esNarrado && sistema));
  boton.setAttribute("aria-label", sistema ? "Volver a la voz narrada" : "Cambiar a la voz del sistema");

  if (estado.aviso && estado.aviso !== ultimoAvisoDeVoz) toast(estado.aviso);
  ultimoAvisoDeVoz = estado.aviso || "";
}

function mensajeDeEstadoLector(estado) {
  if (estado.cargando) return "Cargando capítulo…";
  return Lector.textoActual();
}

function textoRestante(segundos) {
  if (segundos <= 0) return "";
  const minutos = Math.round(segundos / 60);
  if (minutos < 1) return "Menos de 1 min";
  if (minutos < 60) return `≈ ${minutos} min restantes`;
  return `≈ ${Math.floor(minutos / 60)} h ${minutos % 60} min restantes`;
}

let _arrastrandoBarra = false;

function renderLector(estado) {
  if (libroSonando && pantallaActual === "lector") {
    const capitulo = libroSonando.capitulos.find((c) => c.numero === estado.numero);
    const porcentaje = Lector.progreso();

    $("capitulo-actual").textContent = capitulo ? capitulo.titulo : "";
    $("progreso-lector").textContent = `Capítulo ${estado.numero} de ${estado.total}`;
    $("frase-actual").textContent = mensajeDeEstadoLector(estado);
    pintarMotorDeVoz(estado);
    pintarAjustesDeVoz();

    const barra = $("barra-progreso");
    barra.max = Math.max(estado.trozos.length - 1, 1);
    barra.disabled = estado.trozos.length < 2;
    if (!_arrastrandoBarra) {
      barra.value = Math.min(estado.indice, barra.max);
      pintarRelleno(barra);
    }
    $("avance-porcentaje").textContent = `${porcentaje}%`;
    $("avance-restante").textContent = textoRestante(Lector.segundosRestantes());

    const boton = $("btn-reproducir");
    $("icono-reproducir").setAttribute("href", estado.reproduciendo ? "#i-pausa" : "#i-play");
    boton.setAttribute("aria-label", estado.reproduciendo ? "Pausar" : "Reproducir");
    boton.classList.toggle("cargando", estado.cargando);
    $("btn-anterior").disabled = estado.numero <= 1;
    $("btn-siguiente").disabled = estado.numero >= estado.total;
  }
  if (pantallaActual === "libro") marcarCapitulos();
  actualizarMini();
}

// El relleno de la barra se dibuja con una variable CSS.
function pintarRelleno(barra) {
  const maximo = Number(barra.max) || 1;
  barra.style.setProperty("--avance", `${(Number(barra.value) / maximo) * 100}%`);
}

function pintarVelocidades() {
  const caja = $("chips-velocidad");
  caja.innerHTML = "";
  VELOCIDADES.forEach((valor) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = `${valor}×`;
    chip.setAttribute("aria-pressed", String(valor === Lector.estado.velocidad));
    chip.addEventListener("click", () => {
      Lector.setVelocidad(valor);
      pintarVelocidades();
    });
    caja.appendChild(chip);
  });
}

// ---------- Mini reproductor (se ve fuera del lector mientras hay un libro cargado) ----------

function actualizarMini() {
  const barra = $("mini-reproductor");
  const visible =
    Boolean(libroSonando) && Lector.estado.libroId === (libroSonando && libroSonando.id) &&
    pantallaActual !== "lector";
  barra.hidden = !visible;
  document.body.classList.toggle("con-mini", visible);
  if (!visible) return;

  // La portada solo se vuelve a crear si cambió el libro.
  if (barra.dataset.libro !== libroSonando.id) {
    barra.dataset.libro = libroSonando.id;
    $("mini-portada").replaceChildren(
      crearPortada(libroSonando.portada, libroSonando.titulo, "portada-mini")
    );
  }
  const capitulo = libroSonando.capitulos.find((c) => c.numero === Lector.estado.numero);
  const sonando = Lector.estado.reproduciendo;
  $("mini-titulo").textContent = libroSonando.titulo;
  $("mini-capitulo").textContent = capitulo ? etiquetaCapitulo(capitulo) : "";
  $("mini-barra").style.width = `${Lector.progreso()}%`;
  $("mini-icono").setAttribute("href", sonando ? "#i-pausa" : "#i-play");
  $("mini-play").setAttribute("aria-label", sonando ? "Pausar" : "Reproducir");
}

function cargarVoces() {
  const selector = $("selector-voz");
  const voces = Lector.vocesDisponibles();
  selector.innerHTML = "";

  if (voces.length === 0) {
    selector.innerHTML = "<option>Voz predeterminada</option>";
    selector.disabled = true;
    return;
  }
  selector.disabled = false;

  const guardada = Lector.vozGuardada();
  voces.forEach((voz) => {
    const opcion = document.createElement("option");
    opcion.value = voz.name;
    opcion.textContent = `${voz.name} (${voz.lang})`;
    if (voz.name === guardada) opcion.selected = true;
    selector.appendChild(opcion);
  });

  const elegida = voces.find((voz) => voz.name === selector.value) || voces[0];
  if (Lector.estado.voz !== elegida) Lector.setVoz(elegida);
}

// ---------- Eventos ----------

function conectarEventos() {
  window.addEventListener("popstate", alCambiarHistorial);

  document.querySelectorAll("[data-volver]").forEach((boton) => {
    boton.addEventListener("click", volver);
  });

  // Inicio
  $("btn-escuchar").addEventListener("click", () => navegar("biblioteca"));
  $("btn-importar").addEventListener("click", abrirImportacion);
  $("btn-seguir").addEventListener("click", seguirEscuchando);

  // Biblioteca
  $("btn-importar-biblioteca").addEventListener("click", abrirImportacion);
  $("input-buscar").addEventListener("input", pintarBiblioteca);

  // Hojas: botones de cerrar, toque fuera y tecla Escape
  document.querySelectorAll("[data-cerrar-hoja]").forEach((boton) => {
    boton.addEventListener("click", cerrarHoja);
  });
  document.querySelectorAll(".hoja-fondo").forEach((fondo) => {
    fondo.addEventListener("click", (evento) => {
      if (evento.target === evento.currentTarget) cerrarHoja();
    });
  });
  document.addEventListener("keydown", (evento) => {
    if (evento.key === "Escape" && hojaAbierta) cerrarHoja();
  });

  // Importación, paso 1: elegir tipo de archivo.
  const inputEpub = $("input-epub");
  $("opcion-epub").addEventListener("click", () => abrirPasoVoz("epub"));
  $("opcion-pdf").addEventListener("click", () => abrirPasoVoz("pdf"));

  // Paso 2: cómo se va a escuchar (muestra u oculta voz y tono narrados).
  $("btn-continuar-voz").addEventListener("click", () => {
    mostrarPaso(formatoImportacion === "pdf" ? "paso-pdf-tipo" : "paso-epub");
  });

  // Paso 3a: EPUB
  $("btn-elegir-epub").addEventListener("click", () => inputEpub.click());
  inputEpub.addEventListener("change", () => {
    const archivo = inputEpub.files[0];
    inputEpub.value = "";
    if (archivo) importarEpub(archivo);
  });

  // Paso 2b: PDF → se importa en segundo plano
  const inputPdf = $("input-pdf");
  $("btn-elegir-pdf").addEventListener("click", () => inputPdf.click());
  inputPdf.addEventListener("change", () => {
    const archivo = inputPdf.files[0];
    inputPdf.value = "";
    if (!archivo) return;
    const tipo = document.querySelector('input[name="tipo-pdf"]:checked')?.value || "novela";
    importarPdf(archivo, tipo);
  });

  // Libro
  $("btn-continuar-libro").addEventListener("click", () => {
    const progreso = Lector.leerProgreso(libroActual.id);
    leerCapitulo(numeroParaContinuar(libroActual, progreso), { reproducir: true });
  });
  $("btn-menu-libro").addEventListener("click", () => {
    $("menu-libro-titulo").textContent = libroActual.titulo;
    abrirHoja("hoja-menu-libro");
  });

  const inputPortada = $("input-portada");
  $("btn-cambiar-portada").addEventListener("click", () => {
    inputPortada.click();
    cerrarHoja();
  });
  inputPortada.addEventListener("change", () => {
    const archivo = inputPortada.files[0];
    inputPortada.value = "";
    if (archivo) cambiarPortada(archivo);
  });
  $("btn-cambiar-titulo").addEventListener("click", abrirCambioDeTitulo);
  $("form-titulo").addEventListener("submit", guardarTitulo);
  $("btn-cambiar-voz").addEventListener("click", () => abrirCambioDeVoz(libroActual));
  $("btn-borrar-libro").addEventListener("click", abrirConfirmacionDeBorrado);
  $("btn-confirmar-borrar").addEventListener("click", borrarLibroActual);

  // Hoja "Cambiar voz" (desde el menú del libro o desde el lector)
  $("btn-guardar-voz").addEventListener("click", guardarVoz);
  $("btn-motor-voz").addEventListener("click", () => Lector.alternarMotor());
  $("btn-cambiar-voz-lector").addEventListener("click", () => abrirCambioDeVoz(libroSonando));

  // Lector
  $("btn-reproducir").addEventListener("click", () => Lector.alternar());
  $("btn-anterior").addEventListener("click", () => Lector.anterior().catch(avisarCapitulo));
  $("btn-siguiente").addEventListener("click", () => Lector.siguiente().catch(avisarCapitulo));
  $("btn-retroceder").addEventListener("click", () => Lector.saltar(-1));
  $("btn-avanzar").addEventListener("click", () => Lector.saltar(1));

  const barra = $("barra-progreso");
  barra.addEventListener("input", () => {
    _arrastrandoBarra = true;
    pintarRelleno(barra);
  });
  barra.addEventListener("change", () => {
    _arrastrandoBarra = false;
    Lector.irA(Number(barra.value));
  });

  $("selector-voz").addEventListener("change", (evento) => {
    const voz = Lector.vocesDisponibles().find((v) => v.name === evento.target.value);
    if (voz) Lector.setVoz(voz);
  });

  // Barra espaciadora: reproducir o pausar desde el lector (en la PC).
  document.addEventListener("keydown", (evento) => {
    if (evento.code !== "Space" || pantallaActual !== "lector" || hojaAbierta) return;
    if (evento.target.closest("button, input, select, textarea")) return;
    evento.preventDefault();
    Lector.alternar();
  });

  // Mini reproductor
  $("mini-info").addEventListener("click", () => navegar("lector"));
  $("mini-play").addEventListener("click", () => Lector.alternar());

  Lector.onEscuchar(() => {
    Racha.guardar(Racha.registrarEscucha(Racha.cargar()));
  });
  Lector.onCambio(renderLector);

  speechSynthesis.addEventListener("voiceschanged", cargarVoces);
}

function avisarCapitulo() {
  toast("No se pudo cargar el capítulo. Revisá la conexión con la PC.");
}

function iniciar() {
  history.replaceState({ pantalla: "inicio" }, "");
  conectarEventos();
  cargarVoces();
  cargarCatalogoVoces();
  mostrar("inicio");
}

document.addEventListener("DOMContentLoaded", iniciar);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js");
}
