// Service worker mínimo: cachea solo el "cascarón" de la app; la API siempre va a la red.
const CACHE = "fugas-ogi-v1";
const SHELL = ["/", "/static/manifest.webmanifest", "/static/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  const esShell = url.pathname === "/" || url.pathname.startsWith("/static/");
  if (!esShell) return; // /auth, /fugas, /kpis, /cuadrillas: nunca desde caché
  // Red primero (para ver siempre la última versión); caché si no hay conexión.
  e.respondWith(
    fetch(req)
      .then((res) => {
        const copia = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copia));
        return res;
      })
      .catch(() => caches.match(req))
  );
});
