/* FUT Monitor - service worker para notificaciones push en iOS/Android.
   Lo registra la app al activar las notificaciones. */

const ICON = "./icon-192.png";

self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));

self.addEventListener("push", event => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; } catch (_) {
    d = { body: event.data ? event.data.text() : "" };
  }
  const title = d.title || "FUT Monitor";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: d.body || "",
      icon: ICON,
      badge: ICON,
      tag: d.tag || undefined,
      data: { url: d.url || "./" }
    })
  );
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "./";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(list => {
      for (const c of list) {
        if ("focus" in c) return c.focus();
      }
      return self.clients.openWindow(url);
    })
  );
});
