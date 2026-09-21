/* Baby Buddy service worker (babybuddy/babybuddy#128).
 *
 * Makes the app installable and serves the static bundle from cache while it
 * refreshes in the background. Pages themselves always go to the network:
 * this is not an offline mode.
 */
var CACHE = "babybuddy-static-v1";

self.addEventListener("install", function () {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (key) {
              return key !== CACHE;
            })
            .map(function (key) {
              return caches.delete(key);
            }),
        );
      })
      .then(function () {
        return self.clients.claim();
      }),
  );
});

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }
  if (url.pathname.indexOf("/static/") === -1) {
    return;
  }
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      return cache.match(event.request).then(function (cached) {
        var network = fetch(event.request)
          .then(function (response) {
            if (response.ok) {
              cache.put(event.request, response.clone());
            }
            return response;
          })
          .catch(function () {
            return cached;
          });
        return cached || network;
      });
    }),
  );
});
