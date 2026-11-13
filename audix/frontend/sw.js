// Service worker mínimo: deja la app instalable y disponible sin conexión
// para los archivos estáticos. Las llamadas a la API no se cachean.

const CACHE = "audix-v7";
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

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ESTATICOS)));
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches.keys().then((claves) =>
      Promise.all(claves.filter((clave) => clave !== CACHE).map((clave) => caches.delete(clave)))
    )
  );
});

self.addEventListener("fetch", (evento) => {
  if (new URL(evento.request.url).origin !== self.location.origin) return;
  evento.respondWith(
    caches.match(evento.request).then((respuesta) => respuesta || fetch(evento.request))
  );
});
