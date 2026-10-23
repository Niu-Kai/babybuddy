document.addEventListener("DOMContentLoaded", function () {
  const alarm = document.getElementById("feeding-alarm");
  if (!alarm) return;
  const tr = typeof gettext === "function" ? gettext : (value) => value;
  const storagePrefix =
    "babybuddy-feeding:" + alarm.dataset.scope + ":" + alarm.dataset.user;
  const enabledKey = storagePrefix + ":enabled";
  const seen = new Map();
  let enabled = false;
  let audio;
  let busy = false;
  let renderedAlerts;
  try {
    enabled = localStorage.getItem(enabledKey) === "yes";
  } catch (_) {}

  function deviceStatus() {
    document
      .querySelectorAll("[data-feeding-device-status]")
      .forEach(function (node) {
        node.textContent = enabled
          ? tr("Device alerts enabled while the app is open")
          : tr("Device sound and notifications are off");
      });
  }
  function sound() {
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return;
      audio = audio || new Audio();
      audio.resume().catch(function () {});
      for (let index = 0; index < 3; index++) {
        const oscillator = audio.createOscillator();
        const gain = audio.createGain();
        const at = audio.currentTime + index * 0.35;
        oscillator.frequency.value = 660;
        gain.gain.setValueAtTime(0, at);
        gain.gain.linearRampToValueAtTime(0.12, at + 0.03);
        gain.gain.exponentialRampToValueAtTime(0.001, at + 0.25);
        oscillator.connect(gain);
        gain.connect(audio.destination);
        oscillator.start(at);
        oscillator.stop(at + 0.26);
      }
    } catch (_) {
      /* Visual reminders remain available without audio. */
    }
  }
  function announce(row) {
    if (!enabled || !row.ready) return;
    const token = row.reference + ":" + row.due;
    const key = storagePrefix + ":seen:" + row.id;
    const run = function () {
      let previous = seen.get(key);
      try {
        previous = localStorage.getItem(key) || previous;
      } catch (_) {}
      if (previous === token) return;
      seen.set(key, token);
      try {
        localStorage.setItem(key, token);
      } catch (_) {}
      sound();
      if ("Notification" in window && Notification.permission === "granted") {
        try {
          const notification = new Notification(tr("Feeding reminder"), {
            body: row.child + " · " + tr("Time to check for hunger cues"),
            tag: storagePrefix + ":" + row.id,
          });
          notification.onclick = function () {
            window.focus();
            notification.close();
            window.location.assign(row.url);
          };
        } catch (_) {}
      }
    };
    if (navigator.locks)
      navigator.locks
        .request(key, { ifAvailable: true }, (lock) => {
          if (lock) run();
        })
        .catch(function () {});
    else run();
  }
  function render(rows) {
    const ready = rows.filter((row) => row.ready || row.review);
    const signature = JSON.stringify(ready);
    if (signature === renderedAlerts) {
      ready.forEach(announce);
      return;
    }
    renderedAlerts = signature;
    const container = alarm.querySelector("[data-feeding-alerts]");
    container.replaceChildren();
    ready.forEach(function (row) {
      const item = document.createElement("div");
      item.className = "feeding-alarm-row";
      const title = document.createElement("strong");
      title.textContent =
        row.child +
        " · " +
        (row.review ? tr("Review feeding reminder") : tr("Feeding reminder"));
      const link = document.createElement("a");
      link.className = "btn btn-sm btn-primary";
      link.href = row.url;
      link.textContent = row.review ? tr("Choose interval") : tr("Log feeding");
      const snooze = document.createElement("button");
      snooze.type = "button";
      snooze.className = "btn btn-sm btn-outline-secondary";
      snooze.textContent = tr("Remind in 10 minutes");
      snooze.addEventListener("click", async function () {
        snooze.disabled = true;
        try {
          const data = new URLSearchParams({ id: row.id });
          const response = await fetch(alarm.dataset.status, {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: {
              "X-CSRFToken": alarm.querySelector('[name="csrfmiddlewaretoken"]')
                .value,
            },
            body: data,
          });
          if (
            !response.ok ||
            !response.headers.get("Content-Type")?.includes("application/json")
          )
            throw new Error();
          await refresh();
        } catch (_) {
          snooze.textContent = tr("Could not snooze. Try again.");
          snooze.disabled = false;
        }
      });
      item.append(title, link);
      if (!row.review) item.append(snooze);
      container.append(item);
      announce(row);
    });
    alarm.hidden = container.childElementCount === 0;
  }
  async function refresh() {
    if (busy || !navigator.onLine) return;
    busy = true;
    try {
      const response = await fetch(alarm.dataset.status, {
        credentials: "same-origin",
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (
        !response.ok ||
        !response.headers.get("Content-Type")?.includes("application/json")
      )
        throw new Error();
      const data = await response.json();
      render(data.reminders);
    } catch (_) {
      /* Do not sound alarms from stale data or redirect to a login form. */
    } finally {
      busy = false;
    }
  }
  document
    .querySelectorAll("[data-enable-feeding-alerts]")
    .forEach(function (button) {
      button.addEventListener("click", async function () {
        enabled = true;
        try {
          localStorage.setItem(enabledKey, "yes");
        } catch (_) {}
        sound();
        if ("Notification" in window && Notification.permission === "default") {
          try {
            await Notification.requestPermission();
          } catch (_) {}
        }
        deviceStatus();
        await refresh();
      });
    });
  document
    .querySelectorAll("[data-disable-feeding-alerts]")
    .forEach(function (button) {
      button.addEventListener("click", function () {
        enabled = false;
        try {
          localStorage.removeItem(enabledKey);
        } catch (_) {}
        deviceStatus();
      });
    });
  document.querySelectorAll("[data-feeding-plan]").forEach(function (form) {
    const mode = form.querySelector("[data-reminder-mode]");
    const custom = form.querySelector("[data-custom-reminder]");
    const update = function () {
      custom.hidden = mode.value !== "custom";
    };
    mode.addEventListener("change", update);
    update();
  });
  window.addEventListener("storage", function (event) {
    if (event.key === enabledKey) {
      enabled = event.newValue === "yes";
      deviceStatus();
    }
  });
  window.addEventListener("focus", refresh);
  window.addEventListener("online", refresh);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) refresh();
  });
  deviceStatus();
  refresh();
  window.setInterval(refresh, 30000);
});
