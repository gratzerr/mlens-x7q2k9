/* network-first for page loads: a cached index.html must never stick (iOS
   home-screen apps pin HTML aggressively). Falls back to cache only offline.
   v2 (2026-07-24): Generationswechsel + Alt-Cache-Löschung — eine vergiftete
   Kopie vom 21.07. (alter Code + alter QURE-Fehlkurs) wurde bei Netz-Schluckaufen
   immer wieder ausgeliefert. Fallback nur noch aus dem AKTUELLEN Cache, und mit
   kurzem Netz-Timeout, damit ein langsamer Server nicht sofort Cache erzwingt. */
const C = 'pc-v2';
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k))))
    .then(() => clients.claim())
));
self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.mode === 'navigate') {
    e.respondWith(
      fetch(r).then(res => {
        if (res && res.ok) { const cp = res.clone(); caches.open(C).then(c => c.put(r, cp)); }
        return res;
      }).catch(() => caches.open(C).then(c => c.match(r)))
    );
  }
});
