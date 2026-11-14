// Service worker: deja la app instalable y disponible sin conexión para los
// archivos estáticos. Las llamadas a la API no se cachean.
//
// Estrategia "red primero": con conexión siempre se sirve la versión nueva y se
// guarda una copia; la copia solo se usa si la PC no responde. Así no hace falta
// borrar datos del sitio para ver una actualización.

const CACHE = "audix-v11";
const ESTATICOS = [
  "./",
  "index.html",
  "styles.css",
  "config.js",
  "racha.js",
  "mascota.js",
  "lector.js",
  "app.js",
  "manifest.webmanifest",
  "icons/icon-192.png",
  "icons/icon-512.png",
];
const RUTAS_ESTATICAS = new Set(
  ESTATICOS.map((ruta) => new URL(ruta, self.location).pathname)
);

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ESTATICOS))
      // La versión nueva toma el control sin esperar a que se cierren las pestañas.
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((claves) =>
        Promise.all(claves.filter((clave) => clave !== CACHE).map((clave) => caches.delete(clave)))
      )
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (evento) => {
  const url = new URL(evento.request.url);
  if (evento.request.method !== "GET" || url.origin !== self.location.origin) return;
  if (!RUTAS_ESTATICAS.has(url.pathname)) return; // la API va directo a la red

  evento.respondWith(
    fetch(evento.request)
      .then((respuesta) => {
        if (respuesta.ok) {
          const copia = respuesta.clone();
          caches.open(CACHE).then((cache) => cache.put(evento.request, copia));
        }
        return respuesta;
      })
      .catch(() => caches.match(evento.request, { ignoreSearch: true }))
  );
});
