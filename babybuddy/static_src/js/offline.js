/* Offline care log. No API credentials or authenticated pages are cached. */
(async function () {
  "use strict";
  const gettext = window.gettext || ((text) => text);
  const root = document.getElementById("offline-log");
  if (!root) return;
  const scope = root.dataset.scope || "/";
  const byId = (id) => document.getElementById(id);
  const status = (message) => {
    byId("offline-status").textContent = message;
  };
  let profile,
    enabled = false,
    syncing = false,
    editing = null,
    wrongAccount = false,
    editingTimer = null,
    timeReference = null,
    dirty = false;
  const offline = await window.BabyBuddyOffline.ready;
  const { store, save, remove } = offline;
  const entries = async () => offline.entries(profile?.user);
  const select = (id, options) => {
    byId(id).replaceChildren(
      ...options.map(([value, label]) => new Option(label, value)),
    );
  };
  const localDate = () => {
    const now = new Date();
    return new Date(now - now.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  };
  function resetTime() {
    const now = localDate();
    byId("offline-date").value = now.slice(0, 10);
    byId("offline-time").value = now.slice(11, 16);
    timeReference = new Date();
    updateOccurrence();
  }
  function activity() {
    return profile?.activities.find(
      (a) => a.key === byId("offline-activity").value,
    );
  }
  function fields() {
    const current = activity();
    if (!current) return;
    byId("offline-child-wrap").hidden = current.key === "pumping";
    byId("offline-time-wrap").hidden = current.date_only;
    byId("offline-duration-wrap").hidden = !(
      current.duration ?? current.paired
    );
    byId("offline-start-timer").hidden = !current.timer || !!editingTimer;
    byId("offline-unit-wrap").hidden = !current.units.length;
    select("offline-unit", current.units);
    byId("offline-unit").value = current.unit;
    const container = byId("offline-fields");
    container.replaceChildren();
    for (const field of current.fields) {
      const wrap = document.createElement("div");
      wrap.className = "mb-3";
      const label = document.createElement("label");
      label.className = "form-label";
      label.textContent = field.label;
      label.htmlFor = "offline-field-" + field.name;
      const input = document.createElement(
        field.kind === "choice" ? "select" : "input",
      );
      input.id = label.htmlFor;
      input.dataset.field = field.name;
      input.className =
        field.kind === "boolean"
          ? "form-check-input ms-2"
          : field.kind === "choice"
            ? "form-select"
            : "form-control";
      if (field.kind === "choice") {
        if (!field.required) input.add(new Option("—", ""));
        for (const [value, title] of field.choices)
          input.add(new Option(title, value));
      } else {
        input.type =
          field.kind === "boolean"
            ? "checkbox"
            : field.kind === "number"
              ? "number"
              : "text";
      }
      if (field.kind === "number") {
        input.step = "any";
        input.min = "0";
      }
      input.required = field.required && field.kind !== "boolean";
      wrap.append(label, input);
      container.append(wrap);
    }
  }
  function show() {
    byId("offline-enable").hidden = enabled;
    byId("offline-entry").hidden = !enabled || !profile?.activities.length;
    byId("offline-timers-section").hidden = !enabled || wrongAccount;
    if (!profile) return;
    select(
      "offline-child",
      profile.children.map((c) => [c.id, c.name]),
    );
    select(
      "offline-activity",
      profile.activities.map((a) => [a.key, a.label]),
    );
    const requested = new URL(location.href);
    const selected = profile.activities.find(
      (a) =>
        a.add_url &&
        new URL(a.add_url, location.origin).pathname === requested.pathname &&
        (!a.activity_type ||
          String(a.activity_type) ===
            requested.searchParams.get("activity_type")),
    );
    if (selected) byId("offline-activity").value = selected.key;
    const child = profile.children.find(
      (c) =>
        c.slug ===
        (requested.searchParams.get("child") || profile.selected_child),
    );
    if (child) byId("offline-child").value = child.id;
    fields();
    resetTime();
  }
  async function renderQueue() {
    const container = byId("offline-queue");
    container.replaceChildren();
    if (wrongAccount) {
      container.textContent = gettext(
        "Pending entries belong to a different account. Sign in to the original account to view or sync them.",
      );
      return;
    }
    for (const entry of await entries()) {
      const card = document.createElement("article");
      card.className = "card p-3 mb-2";
      const text = document.createElement("p");
      text.textContent =
        entry.label +
        " · " +
        entry.when +
        (entry.error ? " · " + entry.error : gettext(" · Waiting to sync"));
      const discard = document.createElement("button");
      discard.type = "button";
      discard.className = "btn btn-outline-danger btn-sm align-self-start";
      discard.textContent = gettext("Discard");
      discard.addEventListener("click", async () => {
        if (confirm(gettext("Discard this pending entry?"))) {
          await remove(entry.id);
          await renderQueue();
        }
      });
      card.append(text);
      if (entry.status === 400 && entry.format === "form" && entry.formUrl) {
        const url = new URL(entry.formUrl, location.origin);
        if (url.origin === location.origin && url.pathname.startsWith(scope)) {
          url.searchParams.set("local_entry", entry.id);
          const link = document.createElement("a");
          link.className = "btn btn-outline-primary btn-sm mb-2";
          link.href = url.href;
          link.textContent = gettext("Correct entry");
          card.append(link);
        }
      } else if (entry.status === 400 && !syncing) {
        const edit = document.createElement("button");
        edit.type = "button";
        edit.className = "btn btn-outline-primary btn-sm mb-2";
        edit.textContent = gettext("Correct entry");
        edit.addEventListener("click", () => {
          editing = entry.id;
          editingTimer = null;
          byId("offline-activity").value = entry.activity;
          fields();
          byId("offline-child").value = entry.entry.child || "";
          const instant = entry.entry.start || entry.entry.time;
          if (instant) {
            const when = new Date(instant);
            timeReference = when;
            const local = new Date(
              when - when.getTimezoneOffset() * 60000,
            ).toISOString();
            byId("offline-date").value = local.slice(0, 10);
            byId("offline-time").value = local.slice(11, 16);
          } else byId("offline-date").value = entry.entry.date;
          byId("offline-duration").value =
            instant && entry.entry.end
              ? (new Date(entry.entry.end) - new Date(instant)) / 60000
              : 0;
          byId("offline-unit").value = entry.unit || "";
          for (const field of activity().fields) {
            const input = byId("offline-field-" + field.name);
            if (field.kind === "boolean")
              input.checked = Boolean(entry.entry[field.name]);
            else input.value = entry.entry[field.name] ?? "";
          }
          updateOccurrence();
          status(gettext("Correct the entry, then save to retry."));
          byId("offline-entry").scrollIntoView();
        });
        card.append(edit);
      }
      card.append(discard);
      container.append(card);
    }
    if (!container.children.length)
      container.textContent = gettext("No pending entries.");
  }
  const sync = () => offline.sync(true);
  function renderHistory(cached = profile) {
    const section = byId("offline-history-section");
    section.hidden = !enabled || wrongAccount || !cached;
    if (section.hidden) return;
    byId("offline-history-time").textContent = cached.cachedAt
      ? new Date(cached.cachedAt).toLocaleString()
      : "—";
    const list = byId("offline-history");
    list.replaceChildren();
    for (const item of cached.history || []) {
      const card = document.createElement("article");
      card.className = "card p-3 mb-2";
      const title = document.createElement("strong");
      title.textContent = item.label + (item.child ? " · " + item.child : "");
      const when = document.createElement("div");
      when.className = "text-body-secondary";
      when.textContent =
        item.at.length === 10
          ? item.at
          : new Date(item.at).toLocaleString([], {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "numeric",
              minute: "2-digit",
              hour12: !cached.use_24_hour_time,
            });
      const detail = document.createElement("div");
      detail.textContent = item.details;
      card.append(title, when, detail);
      list.append(card);
    }
  }
  byId("offline-entry").addEventListener("input", () => {
    dirty = true;
  });
  window.addEventListener("babybuddy:offline-sync", async ({ detail }) => {
    if (detail.working !== undefined) syncing = detail.working;
    if (detail.wrongAccount !== undefined) {
      const restored = wrongAccount && !detail.wrongAccount;
      wrongAccount = detail.wrongAccount;
      if (wrongAccount) byId("offline-entry").hidden = true;
      else if (restored) {
        editingTimer = null;
        show();
      }
    }
    if (detail.authRequired) byId("offline-history-section").hidden = true;
    if (detail.message) status(detail.message);
    if (detail.profile) {
      profile = detail.profile;
      if (!dirty && !editingTimer && !editing) show();
      renderHistory(profile);
    } else if (wrongAccount) renderHistory();
    await renderQueue();
    await renderTimers();
  });
  function localMinute(when) {
    return new Date(when.getTime() - when.getTimezoneOffset() * 60000)
      .toISOString()
      .slice(0, 16);
  }
  function timeCandidates() {
    const entered =
      byId("offline-date").value + "T" + byId("offline-time").value;
    const naive = Date.parse(entered + "Z");
    if (!Number.isFinite(naive)) return [];
    const offsets = new Set(
      [-86400000, 0, 86400000].map((shift) =>
        new Date(naive + shift).getTimezoneOffset(),
      ),
    );
    return [...offsets]
      .map((offset) => new Date(naive + offset * 60000))
      .filter((date) => localMinute(date) === entered)
      .sort((a, b) => a - b);
  }
  function unchangedTime() {
    return (
      timeReference &&
      localMinute(timeReference) ===
        byId("offline-date").value + "T" + byId("offline-time").value
    );
  }
  function updateOccurrence() {
    const options = timeCandidates();
    byId("offline-occurrence-wrap").hidden =
      options.length !== 2 || unchangedTime();
    select("offline-occurrence", [
      ["", gettext("Choose an occurrence")],
      ...options.map((value, index) => [
        String(index),
        (index === 0 ? gettext("First") : gettext("Second")) +
          " · " +
          value.toLocaleTimeString([], {
            hour: "numeric",
            minute: "2-digit",
            timeZoneName: "short",
          }),
      ]),
    ]);
  }
  function chosenTime() {
    if (unchangedTime()) return timeReference;
    const options = timeCandidates();
    if (!options.length) {
      status(
        gettext(
          "This time does not exist in this time zone. Choose a valid time.",
        ),
      );
      return null;
    }
    if (options.length === 2 && byId("offline-occurrence").value === "") {
      status(
        gettext(
          "This time occurs twice. Choose the first or second occurrence.",
        ),
      );
      return null;
    }
    return options[Number(byId("offline-occurrence").value || 0)];
  }
  byId("offline-date").addEventListener("change", updateOccurrence);
  byId("offline-time").addEventListener("change", updateOccurrence);
  const timers = async () =>
    (await store("readonly", (s) => s.getAll())).filter(
      (v) => v.kind === "timer" && v.user === profile?.user,
    );
  const elapsed = (timer) =>
    timer.elapsed +
    (timer.runningSince === null
      ? 0
      : Math.max(0, Date.now() - timer.runningSince));
  function changeTimer(id, update, queued = null) {
    return new Promise((resolve, reject) => {
      const tx = db.transaction("items", "readwrite");
      const items = tx.objectStore("items");
      const request = items.get(id);
      let result;
      request.onsuccess = () => {
        const current = request.result;
        if (
          !current ||
          current.kind !== "timer" ||
          current.user !== profile?.user ||
          wrongAccount
        ) {
          tx.abort();
          return;
        }
        result = update(current);
        if (queued) {
          items.put(queued);
          items.delete(id);
        } else items.put(result);
      };
      tx.oncomplete = () => resolve(result);
      tx.onabort = tx.onerror = () =>
        reject(
          new Error(
            gettext(
              "This timer changed in another tab. Refresh the timer list.",
            ),
          ),
        );
    });
  }
  const consumeTimer = (id, queued) =>
    changeTimer(id, (current) => current, queued);
  async function renderTimers() {
    const area = byId("offline-timers");
    if (!area) return;
    if (!enabled || wrongAccount) {
      area.replaceChildren();
      byId("offline-timers-section").hidden = true;
      return;
    }
    const list = await timers();
    byId("offline-timers-section").hidden = list.length === 0;
    // Preserve focused buttons while the elapsed labels tick.
    const signature = list
      .map((t) => t.id + ":" + t.runningSince + ":" + t.finished)
      .join("|");
    if (area.dataset.signature === signature) {
      list.forEach((t) => {
        const el = document.getElementById("elapsed-" + t.id);
        if (el)
          el.textContent =
            Math.floor(elapsed(t) / 60000) + " " + gettext("minutes");
      });
      return;
    }
    area.dataset.signature = signature;
    area.replaceChildren();
    for (const timer of list) {
      const card = document.createElement("article");
      card.className = "card p-3 mb-2";
      const title = document.createElement("strong");
      title.textContent = timer.label;
      const duration = document.createElement("p");
      duration.id = "elapsed-" + timer.id;
      duration.textContent =
        Math.floor(elapsed(timer) / 60000) + " " + gettext("minutes");
      card.append(title, duration);
      function button(label, handler) {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-outline-primary btn-sm me-2";
        btn.textContent = label;
        btn.addEventListener("click", async () => {
          btn.disabled = true;
          try {
            await handler();
            await renderTimers();
          } catch (error) {
            status(error.message);
            btn.disabled = false;
          }
        });
        card.append(btn);
      }
      if (!timer.finished)
        button(
          timer.runningSince === null ? gettext("Resume") : gettext("Pause"),
          () =>
            changeTimer(timer.id, (current) => {
              if (current.finished) return current;
              if (current.runningSince === null)
                current.runningSince = Date.now();
              else {
                current.elapsed = elapsed(current);
                current.runningSince = null;
              }
              return current;
            }),
        );
      button(
        timer.finished ? gettext("Review entry") : gettext("Stop and review"),
        async () => {
          const stopped = await changeTimer(timer.id, (current) => {
            current.elapsed = elapsed(current);
            current.runningSince = null;
            current.finished = true;
            return current;
          });
          if (!profile.activities.some((a) => a.key === stopped.activity)) {
            status(
              gettext(
                "This activity is no longer available. The timer remains saved on this device.",
              ),
            );
            return;
          }
          editing = null;
          editingTimer = stopped.id;
          byId("offline-activity").value = stopped.activity;
          fields();
          byId("offline-child").value = stopped.child || "";
          timeReference = new Date(stopped.start);
          const local = localMinute(timeReference);
          byId("offline-date").value = local.slice(0, 10);
          byId("offline-time").value = local.slice(11);
          byId("offline-duration").value = (stopped.elapsed / 60000).toFixed(3);
          byId("offline-unit").value = stopped.unit || "";
          for (const [name, value] of Object.entries(stopped.values)) {
            const input = byId("offline-field-" + name);
            if (input) {
              if (input.type === "checkbox") input.checked = value;
              else input.value = value;
            }
          }
          updateOccurrence();
          status(gettext("Review the details and save the completed entry."));
          byId("offline-entry").scrollIntoView();
        },
      );
      button(gettext("Discard"), async () => {
        if (confirm(gettext("Discard this timer?"))) {
          await remove(timer.id);
          if (editingTimer === timer.id) {
            editingTimer = null;
            fields();
            resetTime();
          }
        }
      });
      area.append(card);
    }
  }
  byId("offline-start-timer").addEventListener("click", async () => {
    if (!enabled || wrongAccount || editingTimer) return;
    const current = activity();
    if (!current?.timer) return;
    const child =
      current.key === "pumping" ? null : Number(byId("offline-child").value);
    if (current.key !== "pumping" && !child)
      return status(gettext("Choose a child."));
    const values = {};
    for (const field of current.fields) {
      const input = byId("offline-field-" + field.name);
      values[field.name] =
        input.type === "checkbox" ? input.checked : input.value;
    }
    const now = Date.now();
    await save({
      id: crypto.randomUUID(),
      kind: "timer",
      user: profile.user,
      activity: current.key,
      child,
      label:
        current.label +
        (child
          ? " · " + profile.children.find((c) => c.id === child).name
          : ""),
      start: new Date(now).toISOString(),
      runningSince: now,
      elapsed: 0,
      values,
      unit: byId("offline-unit").value,
    });
    await renderTimers();
    status(gettext("Timer started on this device."));
  });
  byId("offline-activity").addEventListener("change", fields);
  byId("offline-entry").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const current = activity();
      const date = byId("offline-date").value;
      const time = byId("offline-time").value || "00:00";
      const moment = chosenTime();
      if (!moment) return;
      if (!Number.isFinite(moment.getTime()))
        return status(gettext("Choose a valid date and time."));
      const entry = {};
      if (current.activity_type) entry.activity_type = current.activity_type;
      if (current.key !== "pumping") {
        entry.child = Number(byId("offline-child").value);
        if (!entry.child) return status(gettext("Choose a child."));
      }
      if (current.date_only) entry.date = date;
      else if (current.paired) {
        entry.start = moment.toISOString();
        entry.end = new Date(
          moment.getTime() +
            Number(byId("offline-duration").value || 0) * 60000,
        ).toISOString();
      } else entry.time = moment.toISOString();
      for (const field of current.fields) {
        const input = byId("offline-field-" + field.name);
        if (field.kind === "boolean") entry[field.name] = input.checked;
        else if (input.value !== "")
          entry[field.name] =
            field.kind === "number" ? Number(input.value) : input.value;
      }
      const child = profile.children.find((c) => c.id === entry.child);
      const queued = {
        id: crypto.randomUUID(),
        kind: "entry",
        user: profile.user,
        activity: current.key,
        entry,
        unit: byId("offline-unit").value,
        label: current.label + (child ? " · " + child.name : ""),
        when: date + " " + time,
      };
      if (editingTimer) {
        try {
          await consumeTimer(editingTimer, queued);
        } catch (error) {
          status(error.message);
          return;
        }
        editingTimer = null;
      } else await offline.enqueue(queued);
      if (editing) {
        await remove(editing);
        editing = null;
      }
      status(gettext("Saved on this device."));
      byId("offline-duration").value = "0";
      resetTime();
      fields();
      await renderTimers();
      await renderQueue();
      dirty = false;
      await sync();
    } catch (error) {
      status(error.message);
    }
  });
  window.addEventListener("focus", renderTimers);
  setInterval(renderTimers, 1000);
  profile = await store("readonly", (s) => s.get("profile"));
  enabled = Boolean(profile);
  show();
  renderHistory();
  await renderTimers();
  await renderQueue();
  status(
    enabled
      ? gettext("Offline logging ready for %(name)s.").replace(
          "%(name)s",
          () => profile.username,
        )
      : gettext("Enable while connected before using this page offline."),
  );
  if ("serviceWorker" in navigator)
    await navigator.serviceWorker.register(root.dataset.worker, {
      scope: scope,
    });
  if (enabled) await sync();
})().catch(() => {
  const gettext = window.gettext || ((text) => text);
  const status = document.getElementById("offline-status");
  if (status)
    status.textContent = gettext(
      "Offline storage is unavailable. Check your browser's storage settings.",
    );
});
