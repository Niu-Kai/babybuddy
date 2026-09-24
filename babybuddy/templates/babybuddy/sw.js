/* Baby Buddy service worker (babybuddy/babybuddy#128).
 *
 * Makes the app installable and checks for the current static bundle before falling
 * back to its cached copy. Authenticated pages always use the network;
 * failed navigations open the public offline entry shell.
 */
/* {% load static i18n %}{% get_current_language as LANGUAGE_CODE %} */
var APP_ROOT = "{% url 'babybuddy:root-router' %}";
var CACHE_PREFIX = "babybuddy-static-" + encodeURIComponent(APP_ROOT) + "-";
var CACHE = CACHE_PREFIX + "v11-{{ LANGUAGE_CODE }}";
var STATIC_ROOT = new URL("{% get_static_prefix %}", self.location.origin);
var CATALOG_ROOT = APP_ROOT + "i18n/";
var OFFLINE = "{% url 'babybuddy:entry-add' %}";
var OFFLINE_ASSETS = [
  OFFLINE,
  "{% url 'babybuddy:interface-catalog' LANGUAGE_CODE %}?v=20260922-partial",
  "{% static 'babybuddy/js/offline.js' %}",
  "{% static 'babybuddy/css/app.css' %}",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(CACHE)
      .then(function (cache) {
        return cache.addAll(OFFLINE_ASSETS);
      })
      .then(function () {
        return self.skipWaiting();
      }),
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (key) {
              return key.indexOf(CACHE_PREFIX) === 0 && key !== CACHE;
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

function navigateOrOffline(request) {
  return fetch(request)
    .then(function (response) {
      if (response.status >= 500) throw new Error("Server unavailable");
      return response;
    })
    .catch(function () {
      return caches.match(OFFLINE);
    });
}

self.addEventListener("fetch", function (event) {
  var url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin) {
    return;
  }
  if (url.pathname === OFFLINE) {
    event.respondWith(navigateOrOffline(event.request));
    return;
  }
  if (event.request.mode === "navigate" && url.pathname.startsWith(APP_ROOT)) {
    event.respondWith(navigateOrOffline(event.request));
    return;
  }
  if (
    !(
      url.origin === STATIC_ROOT.origin &&
      url.pathname.startsWith(STATIC_ROOT.pathname)
    ) &&
    !(
      url.pathname.startsWith(CATALOG_ROOT) &&
      /\/i18n\/[a-z0-9-]+\/interface\.js$/i.test(url.pathname)
    )
  ) {
    return;
  }
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      return fetch(event.request)
        .then(function (response) {
          if (!response.ok) throw new Error("Static asset request failed");
          return cache.put(event.request, response.clone()).then(function () {
            return response;
          });
        })
        .catch(function () {
          return cache.match(event.request).then(function (cached) {
            return cached || Response.error();
          });
        });
    }),
  );
});
