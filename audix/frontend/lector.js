// Lector: lee un capítulo en voz alta con la voz del sistema (Web Speech API).
// El texto se divide en trozos cortos porque los navegadores cortan las lecturas largas.
// Guarda el progreso por libro para retomar donde quedaste.

const Lector = (() => {
  const API = AUDIX_API;
  const trozosMaximos = 220;
  const CLAVE_VOZ = "audix-voz";
  const CLAVE_VELOCIDAD = "audix-velocidad";
  // Caracteres por segundo a velocidad 1×, para estimar el tiempo restante.
  const CARACTERES_POR_SEGUNDO = 15;

  const estado = {
    libroId: null,
    numero: 1,
    total: 0,
    trozos: [],
    indice: 0,
    reproduciendo: false,
    cargando: false,
    velocidad: velocidadGuardada(),
    voz: null,
    alEscuchar: null,
    alCambiar: null,
  };

  // Cada lectura lleva una ficha. Al cortar la voz se cambia la ficha, así los
  // eventos que lleguen tarde de un trozo viejo se ignoran y no avanzan dos veces.
  let ficha = 0;

  function cortarVoz() {
    ficha += 1;
    speechSynthesis.cancel();
  }

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

  function borrarProgreso(libroId) {
    localStorage.removeItem(clavProgreso(libroId));
  }

  function notificarCambio() {
    if (estado.alCambiar) estado.alCambiar({ ...estado });
  }

  function hablarSiguiente() {
    if (!estado.reproduciendo) return;

    if (estado.indice >= estado.trozos.length) {
      // Fin del capítulo: pasa al siguiente si existe.
      if (estado.numero < estado.total) {
        cargarCapitulo(estado.numero + 1).then(() => {
          estado.reproduciendo = true;
          notificarCambio();
          hablarSiguiente();
        }).catch(() => {
          estado.reproduciendo = false;
          notificarCambio();
        });
      } else {
        estado.reproduciendo = false;
        notificarCambio();
      }
      return;
    }

    ficha += 1;
    const miFicha = ficha;
    const enunciado = new SpeechSynthesisUtterance(estado.trozos[estado.indice]);
    enunciado.lang = estado.voz ? estado.voz.lang : "es-ES";
    enunciado.rate = estado.velocidad;
    if (estado.voz) enunciado.voice = estado.voz;

    enunciado.onend = () => {
      if (miFicha !== ficha || !estado.reproduciendo) return;
      estado.indice += 1;
      guardarProgreso();
      notificarCambio();
      hablarSiguiente();
    };
    enunciado.onerror = (evento) => {
      if (miFicha !== ficha) return;
      // "interrupted" y "canceled" son normales al pausar o cambiar de capítulo.
      if (evento.error !== "interrupted" && evento.error !== "canceled") {
        estado.reproduciendo = false;
        notificarCambio();
      }
    };

    speechSynthesis.speak(enunciado);
  }

  async function cargarCapitulo(numero, { retomar = false } = {}) {
    cortarVoz();
    estado.cargando = true;
    notificarCambio();
    try {
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
      return datos;
    } finally {
      estado.cargando = false;
      notificarCambio();
    }
  }

  async function abrir(libroId, total, numero = 1) {
    // Si ya está cargado ese mismo capítulo, no se corta la lectura.
    if (estado.libroId === libroId && estado.numero === numero && estado.trozos.length) {
      estado.total = total;
      notificarCambio();
      return null;
    }
    estado.reproduciendo = false;
    estado.libroId = libroId;
    estado.total = total;
    estado.trozos = [];
    estado.indice = 0;
    return cargarCapitulo(numero, { retomar: true });
  }

  // Suelta el libro cargado (por ejemplo, si se borró).
  function cerrar() {
    cortarVoz();
    estado.reproduciendo = false;
    estado.libroId = null;
    estado.trozos = [];
    estado.indice = 0;
    notificarCambio();
  }

  function play() {
    if (!estado.libroId || estado.trozos.length === 0) return;
    if (estado.reproduciendo) return;
    // Si el libro había terminado, vuelve a empezar el capítulo.
    if (estado.indice >= estado.trozos.length && estado.numero >= estado.total) {
      estado.indice = 0;
    }
    estado.reproduciendo = true;
    if (estado.alEscuchar) estado.alEscuchar(estado.libroId);
    notificarCambio();
    hablarSiguiente();
  }

  function pausar() {
    if (!estado.reproduciendo) return;
    estado.reproduciendo = false;
    cortarVoz();
    guardarProgreso();
    notificarCambio();
  }

  function alternar() {
    if (estado.reproduciendo) pausar();
    else play();
  }

  async function cambiarCapitulo(numero) {
    if (numero < 1 || numero > estado.total || estado.cargando) return;
    const estabaReproduciendo = estado.reproduciendo;
    estado.reproduciendo = false;
    await cargarCapitulo(numero);
    if (estabaReproduciendo) play();
  }

  function siguiente() {
    return cambiarCapitulo(estado.numero + 1);
  }

  function anterior() {
    return cambiarCapitulo(estado.numero - 1);
  }

  // Salta a un trozo del capítulo actual (para la barra de progreso).
  function irA(indice) {
    if (estado.trozos.length === 0) return;
    estado.indice = Math.max(0, Math.min(Math.round(indice), estado.trozos.length - 1));
    guardarProgreso();
    if (estado.reproduciendo) {
      cortarVoz();
      hablarSiguiente();
    }
    notificarCambio();
  }

  // Retrocede o avanza algunos trozos (más o menos una oración cada uno).
  function saltar(cantidad) {
    irA(estado.indice + cantidad);
  }

  function setVelocidad(valor) {
    estado.velocidad = valor;
    localStorage.setItem(CLAVE_VELOCIDAD, String(valor));
    if (estado.reproduciendo) {
      // Reinicia el trozo actual con la nueva velocidad.
      cortarVoz();
      hablarSiguiente();
    }
    notificarCambio();
  }

  function velocidadGuardada() {
    const valor = Number(localStorage.getItem(CLAVE_VELOCIDAD));
    return valor >= 0.5 && valor <= 3 ? valor : 1;
  }

  // Guarda el nombre de la voz para usarla también la próxima vez.
  function setVoz(voz) {
    estado.voz = voz;
    if (voz) localStorage.setItem(CLAVE_VOZ, voz.name);
    if (estado.reproduciendo) {
      cortarVoz();
      hablarSiguiente();
    }
  }

  function vozGuardada() {
    return localStorage.getItem(CLAVE_VOZ);
  }

  // Voces en español e inglés, ordenadas por idioma y nombre.
  function vocesDisponibles() {
    return speechSynthesis
      .getVoices()
      .filter((voz) => voz.lang.startsWith("es") || voz.lang.startsWith("en"))
      .sort((a, b) => a.lang.localeCompare(b.lang) || a.name.localeCompare(b.name));
  }

  function progreso() {
    if (estado.trozos.length === 0) return 0;
    return Math.round((estado.indice / estado.trozos.length) * 100);
  }

  // Estimación de los segundos que faltan del capítulo, según la velocidad.
  function segundosRestantes() {
    let caracteres = 0;
    for (let i = estado.indice; i < estado.trozos.length; i += 1) {
      caracteres += estado.trozos[i].length;
    }
    return Math.round(caracteres / (CARACTERES_POR_SEGUNDO * estado.velocidad));
  }

  function textoActual() {
    return estado.trozos[Math.min(estado.indice, estado.trozos.length - 1)] || "";
  }

  function onEscuchar(callback) {
    estado.alEscuchar = callback;
  }

  function onCambio(callback) {
    estado.alCambiar = callback;
  }

  return {
    abrir,
    cerrar,
    play,
    pausar,
    alternar,
    siguiente,
    anterior,
    irA,
    saltar,
    setVelocidad,
    setVoz,
    vocesDisponibles,
    vozGuardada,
    leerProgreso,
    borrarProgreso,
    progreso,
    segundosRestantes,
    textoActual,
    onEscuchar,
    onCambio,
    estado,
  };
})();
