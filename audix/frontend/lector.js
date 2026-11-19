// Lector: lee un capítulo en voz alta. Tiene dos motores:
//   - "narracion": un archivo de audio generado con IA, que el backend arma
//     por capítulo al importar el libro. El capítulo entero es un <audio>, y
//     la posición de lectura se sigue con las "marcas" de tiempo que manda el
//     servidor (una por cada trozo de texto, igual de cortos que los que ya
//     se armaban para la voz del sistema).
//   - "sistema": la voz del navegador (Web Speech API), un trozo a la vez.
//
// Al abrir un capítulo, la prioridad es siempre la narración. Si todavía no
// está generada (el audio del libro se genera en segundo plano), se lee con
// la voz del sistema. Además, se puede pasar a la voz del sistema a mano con
// `alternarMotor()`; esa elección no se guarda: vale hasta cerrar o abrir otro
// libro.
//
// El resto de la app (app.js) no necesita saber cuál de los dos está activo:
// llama a la misma API de siempre (play, pausar, siguiente, saltar...) y el
// motor correcto se elige solo, según `estado.motor`.
//
// Guarda el progreso por libro para retomar donde quedaste.

const Lector = (() => {
  const API = AUDIX_API;
  // 100 caracteres caben siempre en las 3 líneas que muestra la pantalla de reproducción.
  const trozosMaximos = 120;
  const CLAVE_VOZ = "audix-voz";
  const CLAVE_VELOCIDAD = "audix-velocidad";
  // Caracteres por segundo a velocidad 1×, para estimar el tiempo restante
  // con la voz del sistema (con la narración se usa el tiempo real del audio).
  const CARACTERES_POR_SEGUNDO = 15;

  const estado = {
    libroId: null,
    motor: "sistema", // el que está sonando ahora: "sistema" | "narracion"
    motorDelLibro: "sistema", // "narracion" si al libro se le genera audio
    preferirSistema: false,   // el usuario pasó a mano a la voz del sistema
    narracionPendiente: false, // el capítulo es narrado pero su audio todavía no está
    aviso: "",
    textoCapitulo: "",
    numero: 1,
    total: 0,
    trozos: [],      // textos a mostrar, en los dos motores
    marcas: null,    // solo con motor "narracion": [{texto, inicio, fin}] en segundos
    indice: 0,
    reproduciendo: false,
    cargando: false,  // pidiendo el texto del capítulo
    generando: false, // ya no se espera al audio; se mantiene por compatibilidad con app.js
    velocidad: velocidadGuardada(),
    voz: null,
    alEscuchar: null,
    alCambiar: null,
  };

  // Un solo <audio>, reusado para todos los capítulos narrados: cambiar el
  // src alcanza para pasar de uno a otro.
  const audioEl = new Audio();
  audioEl.preload = "auto";

  // Cada lectura lleva una ficha. Al cortar la voz se cambia la ficha, así los
  // eventos que lleguen tarde de un trozo viejo se ignoran y no avanzan dos veces.
  let ficha = 0;

  function cortarVoz() {
    ficha += 1;
    speechSynthesis.cancel();
    audioEl.pause();
  }

  // Pausas en orden de prioridad: el punto corta antes que el punto y coma,
  // y este antes que la coma.
  const pausasPorPrioridad = [/[.!?…]/, /[;:]/, /,/];

  // Posición (después del signo) de la última pausa de ese tipo que entra en el límite.
  function ultimaPausa(texto, marca) {
    let mejor = -1;
    const hasta = Math.min(texto.length, trozosMaximos);
    for (let i = 0; i < hasta; i += 1) {
      const esFinal = i + 1 === texto.length || /\s/.test(texto[i + 1]);
      if (marca.test(texto[i]) && esFinal) mejor = i + 1;
    }
    return mejor;
  }

  // Último recurso: el último espacio que entra en el límite.
  function ultimoEspacio(texto) {
    for (let i = Math.min(texto.length - 1, trozosMaximos); i > 0; i -= 1) {
      if (/\s/.test(texto[i])) return i;
    }
    return Math.min(texto.length, trozosMaximos);
  }

  // Corta el texto eligiendo siempre la pausa de mayor prioridad que entre en el
  // límite; así un trozo termina en punto si hay uno disponible, y solo si no
  // lo hay, en punto y coma, en coma o, en último caso, en un espacio.
  function cortarEnPausas(texto) {
    const trozos = [];
    let resto = texto.trim();
    while (resto.length > trozosMaximos) {
      let corte = -1;
      for (const marca of pausasPorPrioridad) {
        corte = ultimaPausa(resto, marca);
        if (corte > 0) break;
      }
      if (corte <= 0) corte = ultimoEspacio(resto);
      trozos.push(resto.slice(0, corte).trim());
      resto = resto.slice(corte).trim();
    }
    if (resto) trozos.push(resto);
    return trozos;
  }

  // Cada salto de línea es una pausa fuerte; dentro de cada párrafo se aplica la prioridad.
  function partirEnTrozos(texto) {
    return texto
      .split(/\n+/)
      .map((parrafo) => parrafo.trim())
      .filter(Boolean)
      .flatMap(cortarEnPausas);
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

  // Mantiene la pantalla encendida mientras se reproduce, para que Android no
  // pause la voz al bloquearla. En pausa la pantalla se bloquea normal.
  let bloqueoPantalla = null;

  async function sincronizarPantalla() {
    if (!("wakeLock" in navigator)) return;
    try {
      if (estado.reproduciendo && !bloqueoPantalla) {
        bloqueoPantalla = await navigator.wakeLock.request("screen");
        bloqueoPantalla.addEventListener("release", () => {
          bloqueoPantalla = null;
        });
      } else if (!estado.reproduciendo && bloqueoPantalla) {
        const bloqueo = bloqueoPantalla;
        bloqueoPantalla = null;
        await bloqueo.release();
      }
    } catch {
      // El navegador puede negarlo (p. ej. batería baja); la lectura sigue igual.
    }
  }

  // El sistema suelta el bloqueo al ocultar la pestaña: se vuelve a pedir al volver.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") sincronizarPantalla();
  });

  function notificarCambio() {
    sincronizarPantalla();
    if (estado.alCambiar) estado.alCambiar({ ...estado });
  }

  // ---------------------------------------------------------------------
  // Motor "sistema": Web Speech API, un trozo a la vez (como siempre)
  // ---------------------------------------------------------------------

  function hablarSiguiente() {
    if (!estado.reproduciendo) return;

    if (estado.indice >= estado.trozos.length) {
      // Fin del capítulo: pasa al siguiente si existe.
      if (estado.numero < estado.total) {
        cargarCapitulo(estado.numero + 1).then(() => {
          estado.reproduciendo = true;
          notificarCambio();
          continuarReproduccion();
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

  // ---------------------------------------------------------------------
  // Motor "narracion": un <audio> por capítulo, con marcas de tiempo
  // ---------------------------------------------------------------------

  function urlAudio(numero) {
    return `${API}/libros/${estado.libroId}/capitulos/${numero}/audio`;
  }

  // Marcas de tiempo del capítulo si su audio ya está generado; null si todavía no.
  async function pedirMarcas(numero) {
    const respuesta = await Sesion.pedir(`${urlAudio(numero)}/marcas`);
    if (respuesta.status === 404) return null;
    if (!respuesta.ok) throw new Error("No se pudieron cargar los subtítulos del capítulo.");
    return respuesta.json();
  }

  // Pide, sin esperar, que se genere ya el audio de un capítulo (el hilo del
  // libro lo haría igual, pero en su turno). Si falla, no pasa nada.
  function pedirAudio(numero) {
    if (estado.motorDelLibro !== "narracion" || numero < 1 || numero > estado.total) return;
    Sesion.pedir(urlAudio(numero), { method: "POST" }).catch(() => {});
  }

  function usarNarracion(numero, marcas) {
    cortarVoz(); // por si quedó algo sonando del capítulo anterior
    estado.motor = "narracion";
    estado.marcas = marcas;
    estado.trozos = marcas.map((marca) => marca.texto);
    audioEl.src = urlAudio(numero);
    audioEl.playbackRate = estado.velocidad;
    audioEl.load();
  }

  // Fija la posición del audio; si todavía no cargó (recién cambió el src), espera a que pueda.
  function posicionarAudio(segundos) {
    if (audioEl.readyState >= 1) {
      audioEl.currentTime = segundos;
    } else {
      audioEl.addEventListener("loadedmetadata", () => {
        audioEl.currentTime = segundos;
      }, { once: true });
    }
  }

  function usarVozDelSistema() {
    cortarVoz();
    estado.motor = "sistema";
    estado.marcas = null;
    estado.trozos = partirEnTrozos(estado.textoCapitulo);
    audioEl.removeAttribute("src");
    audioEl.load();
  }

  // Dónde caer en otra partición del mismo texto: por proporción de caracteres.
  function indiceEquivalente(desde, hacia, indice) {
    if (!desde.length || !hacia.length) return 0;
    const total = desde.reduce((suma, texto) => suma + texto.length, 0) || 1;
    let antes = 0;
    for (let i = 0; i < Math.min(indice, desde.length); i += 1) antes += desde[i].length;
    const objetivo = (antes / total) * hacia.reduce((suma, texto) => suma + texto.length, 0);
    let acumulado = 0;
    for (let i = 0; i < hacia.length; i += 1) {
      acumulado += hacia[i].length;
      if (acumulado > objetivo) return i;
    }
    return hacia.length - 1;
  }

  function reproducirNarracion() {
    audioEl.play().catch(() => {
      estado.reproduciendo = false;
      notificarCambio();
    });
  }

  function indiceParaTiempo(segundos) {
    const posicion = estado.marcas.findIndex((marca) => segundos < marca.fin);
    return posicion === -1 ? estado.marcas.length - 1 : posicion;
  }

  audioEl.addEventListener("timeupdate", () => {
    if (estado.motor !== "narracion" || !estado.marcas || !estado.marcas.length) return;
    const nuevoIndice = indiceParaTiempo(audioEl.currentTime);
    if (nuevoIndice === estado.indice) return;
    estado.indice = nuevoIndice;
    guardarProgreso();
    notificarCambio();
  });

  audioEl.addEventListener("ended", () => {
    if (estado.motor !== "narracion" || !estado.reproduciendo) return;
    if (estado.numero < estado.total) {
      cargarCapitulo(estado.numero + 1).then(() => {
        estado.reproduciendo = true;
        notificarCambio();
        continuarReproduccion();
      }).catch(() => {
        estado.reproduciendo = false;
        notificarCambio();
      });
    } else {
      estado.reproduciendo = false;
      notificarCambio();
    }
  });

  audioEl.addEventListener("error", () => {
    if (estado.motor !== "narracion" || !estado.reproduciendo) return;
    estado.reproduciendo = false;
    notificarCambio();
  });

  // ---------------------------------------------------------------------
  // API común a los dos motores
  // ---------------------------------------------------------------------

  // Sigue reproduciendo en el motor que corresponda (se usa al pasar de
  // capítulo y al arrancar con play()).
  function continuarReproduccion() {
    if (estado.motor === "narracion") reproducirNarracion();
    else hablarSiguiente();
  }

  async function cargarCapitulo(numero, { retomar = false } = {}) {
    cortarVoz();
    estado.cargando = true;
    estado.aviso = "";
    notificarCambio();
    try {
      const respuesta = await Sesion.pedir(`${API}/libros/${estado.libroId}/capitulos/${numero}`);
      if (!respuesta.ok) throw new Error(`No se pudo cargar el capítulo ${numero}`);
      const datos = await respuesta.json();

      estado.numero = numero;
      estado.textoCapitulo = datos.texto;
      estado.narracionPendiente = false;

      // Prioridad: la narración. Si el audio no está (todavía) o se eligió la
      // voz del sistema, se lee con esa; el capítulo siguiente se vuelve a intentar.
      let marcas = null;
      if (estado.motorDelLibro === "narracion" && !estado.preferirSistema) {
        try {
          marcas = await pedirMarcas(numero);
        } catch {
          marcas = null; // sin conexión con el audio: no se frena la lectura
        }
        if (!marcas) {
          estado.narracionPendiente = true;
          pedirAudio(numero);
        }
      }
      if (marcas) usarNarracion(numero, marcas);
      else usarVozDelSistema();
      if (estado.motorDelLibro === "narracion") pedirAudio(numero + 1);
      estado.indice = 0;

      if (retomar) {
        const progreso = leerProgreso(estado.libroId);
        if (progreso && progreso.numero === numero) {
          estado.indice = Math.min(progreso.indice, estado.trozos.length);
          if (estado.motor === "narracion" && estado.marcas[estado.indice]) {
            posicionarAudio(estado.marcas[estado.indice].inicio);
          }
        }
      }
      guardarProgreso();
      return datos;
    } finally {
      estado.cargando = false;
      notificarCambio();
    }
  }

  // Cambia, en el capítulo que está sonando, entre la narración y la voz del
  // sistema, quedando en el mismo lugar del texto. No se guarda: al abrir un
  // capítulo vuelve a mandar la narración.
  async function alternarMotor() {
    if (estado.motorDelLibro !== "narracion" || !estado.libroId || estado.cargando) return;
    estado.aviso = "";
    const sonaba = estado.reproduciendo;
    const trozosAntes = estado.trozos;
    const indiceAntes = estado.indice;

    if (estado.motor === "narracion") {
      estado.preferirSistema = true;
      usarVozDelSistema();
    } else {
      let marcas = null;
      try {
        marcas = await pedirMarcas(estado.numero);
      } catch {
        marcas = null;
      }
      if (!marcas) {
        pedirAudio(estado.numero);
        estado.aviso = "La narración de este capítulo todavía no está lista.";
        notificarCambio();
        return;
      }
      estado.preferirSistema = false;
      estado.narracionPendiente = false;
      usarNarracion(estado.numero, marcas);
    }

    estado.indice = indiceEquivalente(trozosAntes, estado.trozos, indiceAntes);
    if (estado.motor === "narracion") posicionarAudio(estado.marcas[estado.indice].inicio);
    guardarProgreso();
    estado.reproduciendo = sonaba;
    notificarCambio();
    if (sonaba) continuarReproduccion();
  }

  async function abrir(libroId, total, numero = 1, motor = "sistema") {
    // Si ya está cargado ese mismo capítulo, no se corta la lectura.
    if (estado.libroId === libroId && estado.numero === numero && estado.trozos.length) {
      estado.total = total;
      notificarCambio();
      return null;
    }
    estado.reproduciendo = false;
    estado.libroId = libroId;
    estado.motorDelLibro = motor === "narracion" ? "narracion" : "sistema";
    estado.motor = "sistema";
    estado.preferirSistema = false; // al abrir un capítulo, la prioridad es la narración
    estado.total = total;
    estado.trozos = [];
    estado.marcas = null;
    estado.indice = 0;
    return cargarCapitulo(numero, { retomar: true });
  }

  // Suelta el libro cargado (por ejemplo, si se borró).
  function cerrar() {
    cortarVoz();
    estado.reproduciendo = false;
    estado.libroId = null;
    estado.motorDelLibro = "sistema";
    estado.motor = "sistema";
    estado.preferirSistema = false;
    estado.narracionPendiente = false;
    estado.aviso = "";
    estado.trozos = [];
    estado.marcas = null;
    estado.indice = 0;
    audioEl.removeAttribute("src");
    audioEl.load();
    notificarCambio();
  }

  function play() {
    if (!estado.libroId || estado.trozos.length === 0) return;
    if (estado.reproduciendo) return;
    // Si el libro había terminado, vuelve a empezar el capítulo.
    if (estado.indice >= estado.trozos.length && estado.numero >= estado.total) {
      estado.indice = 0;
      if (estado.motor === "narracion") audioEl.currentTime = 0;
    }
    estado.reproduciendo = true;
    if (estado.alEscuchar) estado.alEscuchar(estado.libroId);
    notificarCambio();
    continuarReproduccion();
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
    if (estado.motor === "narracion") {
      audioEl.currentTime = estado.marcas[estado.indice].inicio;
    } else if (estado.reproduciendo) {
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
    if (estado.motor === "narracion") {
      // El audio no necesita reiniciarse: cambia la velocidad al toque.
      audioEl.playbackRate = valor;
    } else if (estado.reproduciendo) {
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
  // Solo tiene efecto con el motor "sistema"; la voz de la narración se elige
  // al importar el libro (o después, desde "Cambiar voz").
  function setVoz(voz) {
    estado.voz = voz;
    if (voz) localStorage.setItem(CLAVE_VOZ, voz.name);
    if (estado.motor === "sistema" && estado.reproduciendo) {
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

  // Estimación de los segundos que faltan del capítulo. Con la narración se
  // usa el tiempo real del audio (más preciso); con la voz del sistema, una
  // estimación según los caracteres que quedan.
  function segundosRestantes() {
    if (estado.motor === "narracion" && estado.marcas && estado.marcas.length) {
      const fin = estado.marcas[estado.marcas.length - 1].fin;
      return Math.max(0, Math.round((fin - audioEl.currentTime) / estado.velocidad));
    }
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
    alternarMotor,
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
