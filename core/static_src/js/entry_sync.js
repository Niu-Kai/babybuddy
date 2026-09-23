/* Normal add forms use the same durable queue when this device is enabled. */
(function () {
  const config = document.getElementById("offline-sync-config");
  if (!config || !window.BabyBuddyOffline) return;
  const gettext = window.gettext || ((text) => text);
  const byId = (id) => document.getElementById(id);
  let api,
    profile,
    busy = false,
    editing = null;
  const ready = window.BabyBuddyOffline.ready
    .then(async (value) => {
      api = value;
      profile = await api.getProfile();
      await update();
      const key = new URL(location.href).searchParams.get("local_entry");
      const form = document.querySelector("form[data-queued-entry]");
      if (key && form && profile?.user === Number(config.dataset.user)) {
        const item = await api.store("readonly", (s) => s.get(key));
        if (
          item?.user === profile.user &&
          item.format === "form" &&
          item.status === 400 &&
          item.activity.split(":")[0] === form.dataset.queuedEntry
        ) {
          editing = item;
          if (document.readyState === "loading")
            await new Promise((resolve) =>
              document.addEventListener("DOMContentLoaded", resolve, {
                once: true,
              }),
            );
          for (const widget of form.querySelectorAll("[data-meal-foods]")) {
            const rows = widget.querySelector("[data-food-rows]");
            const count =
              item.entry.fields[widget.dataset.fieldName + "_name"]?.length ||
              1;
            while (rows.children.length < Math.min(count, 20))
              rows.append(rows.firstElementChild.cloneNode(true));
          }
          for (const [name, values] of Object.entries(item.entry.fields)) {
            let index = 0;
            for (const input of form.elements) {
              if (input.name !== name || input.type === "file") continue;
              if (["radio", "checkbox"].includes(input.type))
                input.checked = values.includes(input.value);
              else if (input.multiple)
                Array.from(input.options).forEach(
                  (option) => (option.selected = values.includes(option.value)),
                );
              else input.value = values[index++] || "";
            }
          }
          form.dataset.entryTimezone = item.entry.timezone;
          form.dataset.entryTimer = item.entry.timer || "";
          const tags = form.querySelector('[name="tags"]');
          const widget = tags?.closest(".tags-widget");
          if (widget) {
            widget.replaceWith(tags);
            tags.type = "text";
            tags.className = "form-control";
          }
          for (const input of form.elements) {
            input.dispatchEvent(new Event("change", { bubbles: true }));
            if (["left_amount", "right_amount"].includes(input.name))
              input.dispatchEvent(new Event("input", { bubbles: true }));
          }
          message(
            form,
            item.error || gettext("Correct the entry, then save to retry."),
          );
          showOverlap(form, item);
        }
      }
    })
    .catch(() => {});
  function message(form, text) {
    let box = form.querySelector("[data-queue-message]");
    if (!box) {
      box = document.createElement("div");
      box.dataset.queueMessage = "";
      box.className = "alert alert-info";
      box.setAttribute("role", "status");
      form.prepend(box);
    }
    box.textContent = text;
    box.scrollIntoView({ block: "nearest" });
  }
  function showOverlap(form, item) {
    if (!item.fieldErrors?.allow_overlap) return;
    let allow = form.querySelector('[name="allow_overlap"]');
    if (!allow) {
      allow = document.createElement("input");
      allow.name = "allow_overlap";
      allow.id = "queued-allow-overlap";
      const wrap = document.createElement("div");
      wrap.className = "form-check my-3";
      wrap.append(allow);
      form.querySelector("[data-queue-message]").after(wrap);
    }
    allow.type = "checkbox";
    allow.value = "on";
    allow.hidden = false;
    allow.className = "form-check-input";
    if (!form.querySelector('label[for="' + allow.id + '"]')) {
      const label = document.createElement("label");
      label.className = "form-check-label";
      label.textContent = gettext(
        "Save anyway, even though it overlaps another entry",
      );
      label.htmlFor = allow.id;
      allow.after(label);
    }
  }
  async function update(detail = {}) {
    if (!api) return;
    profile = await api.getProfile();
    const own = profile?.user === Number(config.dataset.user);
    const count = own ? (await api.entries(profile.user)).length : 0;
    const indicator = byId("device-sync-indicator");
    if (indicator) {
      indicator.hidden = !count;
      indicator.textContent = gettext("Pending entries") + ": " + count;
    }
    if (byId("device-sync-status")) {
      byId("device-sync-status").textContent =
        detail.message ||
        (profile && !own
          ? gettext("Sign in to the original account to sync pending entries.")
          : own
            ? gettext("Offline access enabled")
            : gettext(
                "Enable while connected before using this page offline.",
              ));
      byId("device-sync-enable").hidden = Boolean(profile);
      byId("device-sync-now").hidden = !own;
      byId("device-sync-clear").hidden = !profile;
    }
  }
  window.addEventListener("babybuddy:offline-sync", ({ detail }) =>
    update(detail).catch(() => {}),
  );
  byId("device-sync-enable")?.addEventListener("click", async (event) => {
    event.currentTarget.disabled = true;
    try {
      await ready;
      profile = await api.enable();
      await update();
      await api.sync();
    } catch (error) {
      byId("device-sync-status").textContent = error.message;
    } finally {
      event.target.disabled = false;
    }
  });
  byId("device-sync-now")?.addEventListener("click", async () => {
    await ready;
    await api.sync();
  });
  byId("device-sync-clear")?.addEventListener("click", async () => {
    if (
      !confirm(
        gettext(
          "Remove all pending entries and offline setup from this device?",
        ),
      )
    )
      return;
    await ready;
    await api.clear();
    await update({ message: gettext("Offline data cleared.") });
  });
  document.addEventListener(
    "submit",
    async (event) => {
      const form = event.target;
      if (!form.matches("form[data-queued-entry]") || form.dataset.nativeSubmit)
        return;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (busy) return;
      busy = true;
      try {
        await ready;
        profile = api && (await api.getProfile());
        if (!profile) {
          form.dataset.nativeSubmit = "true";
          form.requestSubmit(event.submitter || undefined);
          return;
        }
        if (profile.user !== Number(config.dataset.user))
          throw new Error(
            gettext("Sign in to the original account to sync pending entries."),
          );
        const data = new FormData(form);
        const fields = {};
        for (const [name, value] of data) {
          if (value instanceof File) {
            if (value.size)
              throw new Error(gettext("Attachments require a connection."));
            continue;
          }
          if (
            ["csrfmiddlewaretoken", "password", "api_key", "next"].includes(
              name,
            )
          )
            continue;
          (fields[name] ||= []).push(value);
        }
        // A custom activity definition is fixed on the form and is intentionally disabled.
        const definition = form.querySelector('[name="activity_type"]');
        if (definition) fields.activity_type = [definition.value];
        const activity =
          form.dataset.queuedEntry + (definition ? ":" + definition.value : "");
        const id = editing?.id || form.dataset.queueId || crypto.randomUUID();
        const child = profile.children.find(
          (c) => String(c.id) === fields.child?.at(-1),
        );
        const entry = { fields, timezone: form.dataset.entryTimezone };
        if (form.dataset.entryTimer)
          entry.timer = Number(form.dataset.entryTimer);
        const item = {
          id,
          kind: "entry",
          format: "form",
          user: profile.user,
          activity,
          entry,
          label:
            (profile.activities.find((a) => a.key === activity)?.label ||
              activity) + (child ? " · " + child.name : ""),
          when: [
            fields.appointment_date?.[0] || fields.date?.[0],
            fields.start_time?.[0],
          ]
            .filter(Boolean)
            .join(" "),
          formUrl: location.pathname + location.search,
        };
        await api.enqueue(item);
        form.dataset.queueId = id;
        message(form, gettext("Saved on this device."));
        await api.sync();
        const remaining = await api.store("readonly", (s) => s.get(id));
        if (remaining?.status === 400) {
          editing = remaining;
          message(
            form,
            remaining.error || gettext("Please check the highlighted fields."),
          );
          showOverlap(form, remaining);
        } else {
          const cancel = form.querySelector(".form-actions a");
          location.assign(
            remaining
              ? config.dataset.entry + "#pending-entries"
              : cancel?.href || config.dataset.scope,
          );
        }
      } catch (error) {
        message(form, error.message);
      } finally {
        busy = false;
      }
    },
    true,
  );
})();
