'use strict';

// v5.4 retires the offline shell. Telegram WebView caches were able to keep an
// old Mini App release after deployment, so release assets now use explicit
// version parameters and no-store headers instead.
self.addEventListener('install',event=>{
  event.waitUntil(self.skipWaiting());
});

self.addEventListener('activate',event=>{
  event.waitUntil(Promise.all([
    caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith('bb-vg-')).map(key=>caches.delete(key)))),
    self.registration.unregister(),
    self.clients.claim()
  ]));
});
