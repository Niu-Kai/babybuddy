document.addEventListener("DOMContentLoaded", function () {
  const tr = typeof gettext === "function" ? gettext : (value) => value;
  const timer = document.querySelector("[data-contractions]");
  const csrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;
  function duration(seconds) {
    if (seconds === null || seconds === undefined) return "—";
    seconds = Math.max(0, Math.floor(seconds));
    return (
      Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0")
    );
  }
  if (timer) {
    let state = JSON.parse(
      document.getElementById("contraction-initial-state").textContent,
    );
    let offset = new Date(state.now).getTime() - Date.now();
    let busy = false;
    let renderedHistory;
    const clock = timer.querySelector("[data-contraction-clock]");
    const start = timer.querySelector("[data-contraction-start]");
    const stop = timer.querySelector("[data-contraction-stop]");
    const notes = timer.querySelector("#contraction-notes");
    const error = timer.querySelector("[data-contraction-error]");
    const locale = document.documentElement.lang || "en-US";
    const formatter = new Intl.DateTimeFormat(locale, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
      hour12: timer.dataset.clock !== "24",
    });
    function tick() {
      const seconds = state.active
        ? (Date.now() + offset - new Date(state.active.start).getTime()) / 1000
        : 0;
      clock.textContent = duration(seconds);
    }
    function render(next) {
      const priorId = state.active?.id;
      state = next;
      offset = new Date(state.now).getTime() - Date.now();
      if (start) start.hidden = !!state.active;
      if (stop) stop.hidden = !state.active;
      const notesWrap = timer.querySelector("[data-contraction-notes]");
      if (notesWrap) notesWrap.hidden = !state.active;
      if (notes && priorId !== state.active?.id) notes.value = "";
      timer.querySelector("[data-contraction-label]").textContent = state.active
        ? tr("Contraction in progress")
        : tr("Ready when you are");
      timer.querySelector("[data-contraction-count]").textContent = state.count;
      timer.querySelector("[data-contraction-duration]").textContent = duration(
        state.average_duration,
      );
      timer.querySelector("[data-contraction-interval]").textContent = duration(
        state.average_interval,
      );
      const signature = JSON.stringify(
        state.records.map((entry) => [
          entry.id,
          entry.start,
          entry.end,
          entry.end ? entry.duration : null,
          entry.interval,
          entry.notes,
        ]),
      );
      if (signature === renderedHistory) {
        tick();
        return;
      }
      renderedHistory = signature;
      const history = timer.querySelector("[data-contraction-history]");
      history.replaceChildren();
      state.records.forEach(function (entry) {
        const row = document.createElement("tr");
        [
          formatter.format(new Date(entry.start)),
          entry.end ? duration(entry.duration) : tr("In progress"),
          duration(entry.interval),
          entry.notes || "—",
        ].forEach(function (value) {
          const cell = document.createElement("td");
          cell.textContent = value;
          row.append(cell);
        });
        if (timer.dataset.canDelete === "true") {
          const cell = document.createElement("td");
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn btn-sm btn-outline-secondary";
          button.setAttribute("aria-label", tr("Delete contraction"));
          const icon = document.createElement("i");
          icon.className = "icon-delete";
          icon.setAttribute("aria-hidden", "true");
          button.append(icon);
          button.addEventListener("click", function () {
            if (window.confirm(tr("Delete this contraction?")))
              request("delete", entry.id);
          });
          cell.append(button);
          row.append(cell);
        }
        history.append(row);
      });
      if (!state.records.length) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = timer.dataset.canDelete === "true" ? 5 : 4;
        cell.textContent = tr("No contractions recorded yet.");
        row.append(cell);
        history.append(row);
      }
      tick();
    }
    async function request(action, id) {
      if (busy) return;
      busy = true;
      if (start) start.disabled = true;
      if (stop) stop.disabled = true;
      try {
        const options = {
          credentials: "same-origin",
          cache: "no-store",
          headers: { Accept: "application/json" },
        };
        if (action) {
          options.method = "POST";
          options.headers["X-CSRFToken"] = csrf;
          options.body = new URLSearchParams({
            action,
            id: id || "",
            notes: notes?.value || "",
          });
        }
        const response = await fetch(timer.dataset.url, options);
        if (!response.ok) throw new Error();
        render(await response.json());
        error.hidden = true;
      } catch (_) {
        error.textContent = tr(
          "Could not reach the server. Your last saved timer is shown; reconnect and try again.",
        );
        error.hidden = false;
      } finally {
        busy = false;
        if (start) start.disabled = false;
        if (stop) stop.disabled = false;
      }
    }
    if (start) start.addEventListener("click", () => request("start"));
    if (stop)
      stop.addEventListener("click", () => request("stop", state.active?.id));
    render(state);
    window.setInterval(tick, 250);
    window.setInterval(() => request(), 10000);
    window.addEventListener("focus", () => request());
  }
  document.querySelectorAll("[data-pack-item]").forEach(function (form) {
    const checkbox = form.querySelector('[type="checkbox"]');
    checkbox.addEventListener("change", async function () {
      const wanted = checkbox.checked;
      const data = new FormData(form);
      data.set("packed", wanted ? "1" : "0");
      checkbox.disabled = true;
      const error = document.querySelector("[data-packing-error]");
      try {
        // A hidden field named "action" shadows HTMLFormElement.action.
        const response = await fetch(
          form.getAttribute("action") || window.location.href,
          {
            method: "POST",
            credentials: "same-origin",
            cache: "no-store",
            headers: { Accept: "application/json" },
            body: data,
          },
        );
        if (!response.ok) throw new Error();
        const result = await response.json();
        form.querySelector('[name="packed"]').value = wanted ? "0" : "1";
        document.querySelector("[data-packing-count]").textContent =
          result.packed + " / " + result.total;
        error.hidden = true;
      } catch (_) {
        checkbox.checked = !wanted;
        error.textContent = tr(
          "Could not save this item. Reconnect and try again.",
        );
        error.hidden = false;
      } finally {
        checkbox.disabled = false;
      }
    });
    form.addEventListener("submit", function (event) {
      event.preventDefault();
    });
  });
});
