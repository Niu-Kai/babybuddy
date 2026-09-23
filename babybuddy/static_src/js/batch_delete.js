(() => {
  const form = document.getElementById("batch-delete");
  if (!form) return;
  const progress = document.getElementById("delete-progress");
  const status = document.getElementById("delete-status");
  const submit = form.querySelector('[type="submit"]');
  const stop = document.getElementById("stop-delete");
  let running = false,
    stopping = false;
  stop.addEventListener("click", () => {
    stopping = true;
    stop.disabled = true;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (running) return;
    running = true;
    stopping = false;
    submit.disabled = true;
    stop.hidden = false;
    stop.disabled = false;
    try {
      while (!stopping) {
        const body = new FormData(form);
        body.set("position", form.dataset.position);
        const response = await fetch(location.href, {
          method: "POST",
          body,
          credentials: "same-origin",
          headers: { Accept: "application/json" },
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || form.dataset.stopped);
        form.dataset.position = String(result.position);
        progress.value = result.position;
        status.textContent =
          result.position +
          " / " +
          result.total +
          " · " +
          result.deleted +
          " " +
          form.dataset.deletedLabel +
          " · " +
          result.skipped +
          " " +
          form.dataset.skippedLabel;
        if (result.done) {
          status.textContent += " · " + form.dataset.completed;
          return;
        }
      }
      status.textContent += " · " + form.dataset.stopped;
    } catch (error) {
      status.textContent = error.message + " " + form.dataset.stopped;
    } finally {
      running = false;
      stop.hidden = true;
      submit.disabled =
        Number(form.dataset.position) >= Number(form.dataset.total);
    }
  });
})();
