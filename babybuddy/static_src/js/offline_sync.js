/* Shared, device-local queue. Authenticated HTML and credentials are never cached. */
(function () {
  "use strict";
  const config =
    document.getElementById("offline-log") ||
    document.getElementById("offline-sync-config");
  if (!config) return;
  const gettext = window.gettext || ((text) => text);
  const scope = config.dataset.scope || "/";
  const dbName = "babybuddy-offline-v1" + (scope === "/" ? "" : ":" + scope);
  const INTERVAL = 5 * 60 * 1000;
  const ready = new Promise((resolve, reject) => {
    const request = indexedDB.open(dbName, 1);
    request.onupgradeneeded = () =>
      request.result.createObjectStore("items", { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }).then((db) => {
    function store(mode, action) {
      return new Promise((resolve, reject) => {
        const tx = db.transaction("items", mode);
        const request = action(tx.objectStore("items"));
        tx.oncomplete = () => resolve(request.result);
        tx.onerror = tx.onabort = () =>
          reject(tx.error || new Error("Local storage transaction failed"));
      });
    }
    const save = (value) => store("readwrite", (s) => s.put(value));
    const remove = (id) => store("readwrite", (s) => s.delete(id));
    const getProfile = () => store("readonly", (s) => s.get("profile"));
    const entries = async (user) =>
      (await store("readonly", (s) => s.getAll())).filter(
        (v) => v.kind === "entry" && v.user === user,
      );
    let running = null;
    let repeat = false;
    let generation = 0;
    function notify(detail) {
      window.dispatchEvent(
        new CustomEvent("babybuddy:offline-sync", { detail }),
      );
    }
    async function request(url, options = {}) {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 10000);
      try {
        return await fetch(url, {
          credentials: "same-origin",
          cache: "no-store",
          ...options,
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
    }
    async function freshProfile() {
      const response = await request(config.dataset.context);
      if (!response.ok) {
        const error = new Error(
          gettext("Sign in to Baby Buddy before syncing."),
        );
        error.status = response.status;
        throw error;
      }
      return response.json();
    }
    async function cacheProfile(fresh) {
      const { csrf, ...cached } = fresh;
      cached.cachedAt = Date.now();
      await save({ ...cached, id: "profile" });
      return cached;
    }
    async function perform(force) {
      const version = generation;
      const profile = await getProfile();
      if (!profile) return;
      const owner = Number(config.dataset.user || profile.user);
      if (owner !== profile.user) {
        notify({
          wrongAccount: true,
          message: gettext(
            "Sign in to the original account to sync pending entries.",
          ),
        });
        return;
      }
      const state = await store("readonly", (s) => s.get("sync-state"));
      if (
        !force &&
        state?.user === owner &&
        Date.now() - state.attemptedAt < INTERVAL
      )
        return;
      await save({ id: "sync-state", user: owner, attemptedAt: Date.now() });
      notify({ working: true });
      let pending = [];
      try {
        let fresh = await freshProfile();
        if (fresh.user !== owner) {
          notify({
            wrongAccount: true,
            message: gettext(
              "Sign in to the original account to sync pending entries.",
            ),
          });
          return;
        }
        pending = await entries(owner);
        for (const item of pending) {
          if (version !== generation) return;
          const response = await request(config.dataset.sync, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": fresh.csrf,
            },
            body: JSON.stringify({
              user: item.user,
              key: item.id,
              activity: item.activity,
              entry: item.entry,
              unit: item.unit,
              ...(item.format ? { format: item.format } : {}),
            }),
          });
          // A lost response leaves the UUID intact; the server deduplicates retries.
          if (response.ok) {
            const result = await response.json();
            if (!result.id || result.activity !== item.activity)
              throw new Error("Invalid sync confirmation");
            notify({ saved: item.id, result });
            await remove(item.id);
          } else {
            const error = await response.json().catch(() => ({}));
            item.error = Object.entries(error)
              .map(
                ([key, value]) =>
                  key + ": " + (Array.isArray(value) ? value.join(" ") : value),
              )
              .join(" · ");
            item.status = response.status;
            item.fieldErrors = error;
            if (version === generation) await save(item);
            if (
              response.status === 401 ||
              response.status === 403 ||
              response.status >= 500
            )
              break;
          }
        }
        // Refresh after writes, so cached history includes the entries just synced.
        if (pending.length) fresh = await freshProfile();
        if (version !== generation) return;
        if (fresh.user !== owner) {
          notify({
            wrongAccount: true,
            message: gettext(
              "Sign in to the original account to sync pending entries.",
            ),
          });
          return;
        }
        const current = await getProfile();
        if (!current || current.user !== owner) return;
        const cached = await cacheProfile(fresh);
        const remaining = (await entries(owner)).length;
        notify({
          profile: cached,
          wrongAccount: false,
          pending: remaining,
          message: remaining
            ? gettext(
                "Some entries need attention. They remain on this device.",
              )
            : gettext("All entries synced."),
        });
      } catch (error) {
        notify({
          authRequired: error.status === 401 || error.status === 403,
          message: error.status
            ? error.message
            : gettext("Offline · entries stay on this device until connected."),
        });
      } finally {
        notify({ working: false });
      }
    }
    function sync(force = true) {
      if (running) {
        if (force) repeat = true;
        return running;
      }
      const work = async () => {
        do {
          repeat = false;
          await perform(force);
          if (repeat) force = true;
        } while (repeat);
      };
      running = (
        navigator.locks
          ? navigator.locks.request(dbName + ":sync", work)
          : work()
      )
        .catch(() => {
          notify({
            message: gettext(
              "Offline storage is unavailable. Check your browser's storage settings.",
            ),
          });
        })
        .finally(() => {
          running = null;
        });
      return running;
    }
    async function enable() {
      if (!("serviceWorker" in navigator))
        throw new Error(
          gettext(
            "Offline logging requires HTTPS or localhost and a supported browser.",
          ),
        );
      const fresh = await freshProfile();
      const existing = await getProfile();
      if (existing && existing.user !== fresh.user)
        throw new Error(
          gettext("Sign in to the original account to sync pending entries."),
        );
      const worker = config.dataset.worker;
      if (worker) await navigator.serviceWorker.register(worker, { scope });
      const cached = await cacheProfile(fresh);
      notify({
        profile: cached,
        pending: (await entries(cached.user)).length,
        wrongAccount: false,
      });
      return cached;
    }
    async function enqueue(item) {
      const profile = await getProfile();
      if (
        !profile ||
        item.user !== profile.user ||
        (config.dataset.user && Number(config.dataset.user) !== profile.user)
      )
        throw new Error(
          gettext("Sign in to the original account to sync pending entries."),
        );
      await save(item);
      notify({ pending: (await entries(profile.user)).length });
    }
    async function clear() {
      generation++;
      // Prevent an in-flight response from recreating cleared device data.
      if (running) await running;
      const erase = () => store("readwrite", (s) => s.clear());
      if (navigator.locks)
        await navigator.locks.request(dbName + ":sync", erase);
      else await erase();
      notify({ cleared: true });
    }
    const wake = () => {
      if (!document.hidden) sync(true);
    };
    window.addEventListener("online", wake);
    window.addEventListener("pageshow", wake);
    window.addEventListener("focus", wake);
    document.addEventListener("visibilitychange", wake);
    setInterval(() => {
      if (!document.hidden) sync(false);
    }, INTERVAL);
    return {
      store,
      save,
      remove,
      getProfile,
      freshProfile,
      cacheProfile,
      enable,
      enqueue,
      entries,
      sync,
      clear,
      interval: INTERVAL,
    };
  });
  window.BabyBuddyOffline = { ready };
  // The offline form initializes its listeners before starting its first sync.
  if (!document.getElementById("offline-log"))
    ready.then((api) => api.sync(true)).catch(() => {});
})();
