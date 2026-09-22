document.addEventListener("DOMContentLoaded", function () {
  const toolbar = document.querySelector("[data-dashboard-arrange]");
  if (!toolbar) return;
  const status = toolbar.querySelector("[data-arrange-status]");
  let dragging = null;
  function sync(source) {
    const order = Array.from(source.children).map(
      (cell) => cell.dataset.dashboardPanel,
    );
    document.querySelectorAll(".dash-grid").forEach((grid) => {
      order.forEach((key) => {
        const cell = Array.from(grid.children).find(
          (node) => node.dataset.dashboardPanel === key,
        );
        if (cell) grid.appendChild(cell);
      });
    });
  }
  toolbar
    .querySelector("[data-arrange-start]")
    .addEventListener("click", function () {
      document.body.classList.add("arranging-panels");
      this.hidden = true;
      toolbar.querySelector("[data-arrange-save]").hidden = false;
      toolbar.querySelector("[data-arrange-cancel]").hidden = false;
      document.querySelectorAll(".dash").forEach((dashboard) => {
        const grids = dashboard.querySelectorAll(".dash-grid");
        if (!grids.length) return;
        grids.forEach((grid, index) => {
          if (index) {
            Array.from(grid.children).forEach((cell) =>
              grids[0].appendChild(cell),
            );
            grid.closest(".dash-section").hidden = true;
          }
        });
        dashboard
          .querySelectorAll(".panel-move-controls")
          .forEach((control) => (control.hidden = false));
        dashboard
          .querySelectorAll(".panel-drag")
          .forEach((handle) => (handle.draggable = true));
      });
    });
  document.addEventListener("click", function (event) {
    const button = event.target.closest("[data-panel-move]");
    if (!button || !document.body.classList.contains("arranging-panels"))
      return;
    const cell = button.closest(".dash-cell"),
      grid = cell.parentElement;
    if (button.dataset.panelMove === "-1" && cell.previousElementSibling)
      grid.insertBefore(cell, cell.previousElementSibling);
    if (button.dataset.panelMove === "1" && cell.nextElementSibling)
      grid.insertBefore(cell.nextElementSibling, cell);
    sync(grid);
    button.focus();
  });
  document.addEventListener("dragstart", function (event) {
    if (
      !event.target.matches(".panel-drag") ||
      !document.body.classList.contains("arranging-panels")
    )
      return;
    dragging = event.target.closest(".dash-cell");
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", dragging.dataset.dashboardPanel);
    event.dataTransfer.setDragImage(dragging, 20, 20);
    dragging.classList.add("panel-dragging");
  });
  document.addEventListener("dragover", function (event) {
    const target = event.target.closest(".dash-cell");
    if (dragging && target && target.parentElement === dragging.parentElement)
      event.preventDefault();
  });
  document.addEventListener("drop", function (event) {
    const target = event.target.closest(".dash-cell");
    if (
      !dragging ||
      !target ||
      target === dragging ||
      target.parentElement !== dragging.parentElement
    )
      return;
    event.preventDefault();
    const grid = target.parentElement;
    const cells = Array.from(grid.children);
    grid.insertBefore(
      dragging,
      cells.indexOf(dragging) < cells.indexOf(target)
        ? target.nextSibling
        : target,
    );
    sync(grid);
  });
  document.addEventListener("dragend", function () {
    if (dragging) dragging.classList.remove("panel-dragging");
    dragging = null;
  });
  toolbar
    .querySelector("[data-arrange-cancel]")
    .addEventListener("click", () => window.location.reload());
  toolbar
    .querySelector("[data-arrange-save]")
    .addEventListener("click", async function () {
      const grid = document.querySelector(".dash-grid");
      if (!grid || !grid.children.length) {
        window.location.reload();
        return;
      }
      const data = new FormData();
      data.set(
        "csrfmiddlewaretoken",
        toolbar.querySelector("[name=csrfmiddlewaretoken]").value,
      );
      data.set("action", "reorder");
      Array.from(grid.children).forEach((cell) =>
        data.append("order", cell.dataset.dashboardPanel),
      );
      this.disabled = true;
      try {
        const response = await fetch(toolbar.dataset.saveUrl, {
          method: "POST",
          body: data,
          credentials: "same-origin",
        });
        if (!response.ok || !(await response.json()).saved)
          throw new Error("Save failed");
        window.location.reload();
      } catch (error) {
        status.textContent = status.dataset.error;
        this.disabled = false;
      }
    });
});
