// Lector: lee un capítulo en voz alta con la voz del sistema (Web Speech API).
// El texto se divide en trozos cortos porque los navegadores cortan las lecturas largas.
// Guarda el progreso por libro para retomar donde quedaste.

const Lector = (() => {
  const API = AUDIX_API;
  const trozosMaximos = 220;

  const estado = {
    libroId: null,
    numero: 1,
    total: 0,
    trozos: [],
    indice: 0,
    reproduciendo: false,
    velocidad: 1,
    voz: null,
    alEscuchar: null,
    alCambiar: null,
  };

  function partirEnTrozos(texto) {
    const frases = texto
      .split(/(?<=[.!?…])\s+|\n+/)
      .map((frase) => frase.trim())
      .filter(Boolean);

    const trozos = [];
    let actual = "";
    for (const frase of frases) {
      const candidato = actual ? `${actual} ${frase}` : frase;
      if (candidato.length > trozosMaximos && actual) {
        trozos.push(actual);
        actual = frase;
      } else {
        actual = candidato;
      }
    }
    if (actual) trozos.push(actual);
    return trozos;
  }

  function clavProgreso(libroId) {
    return `audix-progreso-${libroId}`;
  }

  function guardarProgreso() {
    if (!estado.libroId) return;
    localStorage.setItem(
      clavProgreso(estado.libroId),
      JSON.stringify({ numero: estado.numero, indice: estado.indice })
    );
  }

  function leerProgreso(libroId) {
    try {
      return JSON.parse(localStorage.getItem(clavProgreso(libroId))) || null;
    } catch {
      return null;
    }
  }

  function notificarCambio() {
    if (estado.alCambiar) estado.alCambiar({ ...estado });
  }

  function hablarSiguiente() {
    if (!estado.reproduciendo) return;

    if (estado.indice >= estado.trozos.length) {
      // Fin del capítulo: pasa al siguiente si existe.
      if (estado.numero < estado.total) {
        cargarCapitulo(estado.numero + 1).then(() => play());
      } else {
        estado.reproduciendo = false;
        notificarCambio();
      }
      return;
    }

    const enunciado = new SpeechSynthesisUtterance(estado.trozos[estado.indice]);
    enunciado.lang = "es-ES";
    enunciado.rate = estado.velocidad;
    if (estado.voz) enunciado.voice = estado.voz;

    enunciado.onend = () => {
      if (!estado.reproduciendo) return;
      estado.indice += 1;
      guardarProgreso();
      notificarCambio();
      hablarSiguiente();
    };
    enunciado.onerror = (evento) => {
      // "interrupted" y "canceled" son normales al pausar o cambiar de capítulo.
      if (evento.error !== "interrupted" && evento.error !== "canceled") {
        estado.reproduciendo = false;
        notificarCambio();
      }
    };

    speechSynthesis.speak(enunciado);
  }

  async function cargarCapitulo(numero, { retomar = false } = {}) {
    speechSynthesis.cancel();
    const respuesta = await fetch(`${API}/libros/${estado.libroId}/capitulos/${numero}`);
    if (!respuesta.ok) throw new Error(`No se pudo cargar el capítulo ${numero}`);
    const datos = await respuesta.json();

    estado.numero = numero;
    estado.trozos = partirEnTrozos(datos.texto);
    estado.indice = 0;

    if (retomar) {
      const progreso = leerProgreso(estado.libroId);
      if (progreso && progreso.numero === numero) {
        estado.indice = Math.min(progreso.indice, estado.trozos.length);
      }
    }
    guardarProgreso();
    notificarCambio();
    return datos;
  }

  async function abrir(libroId, total, numero = 1) {
    estado.libroId = libroId;
    estado.total = total;
    return cargarCapitulo(numero, { retomar: true });
  }

  function play() {
    if (!estado.libroId || estado.trozos.length === 0) return;
    if (estado.reproduciendo && speechSynthesis.paused) {
      speechSynthesis.resume();
      return;
    }
    estado.reproduciendo = true;
    if (estado.alEscuchar) estado.alEscuchar(estado.libroId);
    notificarCambio();
    hablarSiguiente();
  }

  function pausar() {
    if (!estado.reproduciendo) return;
    estado.reproduciendo = false;
    speechSynthesis.cancel();
    guardarProgreso();
    notificarCambio();
  }

  async function siguiente() {
    if (estado.numero >= estado.total) return;
    const estabaReproduciendo = estado.reproduciendo;
    estado.reproduciendo = false;
    await cargarCapitulo(estado.numero + 1);
    if (estabaReproduciendo) play();
  }

  async function anterior() {
    if (estado.numero <= 1) return;
    const estabaReproduciendo = estado.reproduciendo;
    estado.reproduciendo = false;
    await cargarCapitulo(estado.numero - 1);
    if (estabaReproduciendo) play();
  }

  function setVelocidad(valor) {
    estado.velocidad = valor;
    if (estado.reproduciendo) {
      // Reinicia el trozo actual con la nueva velocidad.
      speechSynthesis.cancel();
      hablarSiguiente();
    }
  }

  function setVoz(voz) {
    estado.voz = voz;
  }

  function vocesEspanol() {
    return speechSynthesis.getVoices().filter((voz) => voz.lang.startsWith("es"));
  }

  function progreso() {
    if (estado.trozos.length === 0) return 0;
    return Math.round((estado.indice / estado.trozos.length) * 100);
  }

  function onEscuchar(callback) {
    estado.alEscuchar = callback;
  }

  function onCambio(callback) {
    estado.alCambiar = callback;
  }

  return {
    abrir,
    play,
    pausar,
    siguiente,
    anterior,
    setVelocidad,
    setVoz,
    vocesEspanol,
    progreso,
    onEscuchar,
    onCambio,
    estado,
  };
})();
