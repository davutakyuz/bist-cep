// BIST Cep service worker: yalnızca bildirim alır ve dokunulunca uygulamayı açar (önbellekleme yok;
// sayfa her açılışta güncel sürümü internetten yükler).
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

// uygulama sayfasının kendisi önbelleği atlayarak yüklenir (GitHub Pages 10 dk önbellekliyor; düzeltmeler geç geliyordu);
// ağ yoksa tarayıcının elindeki kopya
self.addEventListener("fetch", e => {
  if (e.request.mode !== "navigate") return;
  e.respondWith(fetch(e.request, { cache: "no-store" }).catch(() => fetch(e.request)));
});

self.addEventListener("push", e => {
  let v = {};
  try { v = e.data ? e.data.json() : {} } catch { v = { govde: e.data && e.data.text() } }
  e.waitUntil(self.registration.showNotification(v.baslik || "BIST Cep", {
    body: v.govde || "Borsa açıldı; fiyatlar güncellendi.",
    icon: "ikon-192.png", badge: "ikon-192.png", tag: v.etiket || "bistcep", data: { url: v.url || "./" },
  }));
});

self.addEventListener("notificationclick", e => {
  e.notification.close();
  const hedef = new URL(e.notification.data?.url || "./", self.registration.scope).href;
  e.waitUntil((async () => {
    const pencereler = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const p of pencereler) if (p.url.startsWith(self.registration.scope)) { await p.focus(); return }
    await self.clients.openWindow(hedef);
  })());
});
