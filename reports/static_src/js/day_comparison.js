function initializeDayComparisons(event) {
  const root =
    event && event.detail && event.detail.root ? event.detail.root : document;
  const observers = [];
  let disposed = false;
  let retryTimer;

  const grids = Array.from(root.querySelectorAll("[data-day-comparison]"));
  if (!grids.length) return;
  grids[0].dayCleanup = function () {
    disposed = true;
    clearTimeout(retryTimer);
    observers.forEach(function (observer) {
      observer.disconnect();
    });
  };
  const day = 86400000;
  const starts = grids.map(function (grid) {
    return Date.parse(grid.dataset.firstDay + "T00:00:00Z") / day;
  });
  const first = Math.min.apply(null, starts);
  const last = Math.max.apply(
    null,
    grids.map(function (grid, i) {
      return starts[i] + Number(grid.dataset.dayCount) - 1;
    }),
  );
  let cursor = first;
  let pageSize = 3;
  let lastState = "";
  const format = new Intl.DateTimeFormat(
    document.documentElement.lang || "en-US",
    {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    },
  );
  function render() {
    pageSize = Math.max(
      1,
      Math.min.apply(
        null,
        grids.map(function (grid) {
          return Math.max(
            1,
            Math.floor(
              (grid.clientWidth - 120) / Number(grid.dataset.dayWidth),
            ),
          );
        }),
      ),
    );
    pageSize = Math.min(pageSize, last - first + 1);
    cursor = Math.max(first, Math.min(cursor, last - pageSize + 1));
    const state = cursor + ":" + pageSize;
    const ready = grids.every(function (grid) {
      const chart = grid.querySelector(".plotly-graph-div");
      return window.Plotly && chart && chart._fullLayout;
    });
    if (!ready) return false;
    if (state === lastState) return true;
    lastState = state;
    grids.forEach(function (grid, i) {
      const chart = grid.querySelector(".plotly-graph-div");
      const update = {
        "xaxis.range": [
          cursor - starts[i] - 0.5,
          cursor - starts[i] + pageSize - 0.5,
        ],
        "xaxis.autorange": false,
      };
      if (chart.layout && chart.layout.annotations) {
        update.annotations = chart.layout.annotations.map(
          function (annotation) {
            return Object.assign({}, annotation, {
              visible:
                annotation.x >= cursor - starts[i] - 0.5 &&
                annotation.x < cursor - starts[i] + pageSize - 0.5,
            });
          },
        );
      }
      Plotly.relayout(chart, update);
      grid.querySelector("[data-day-previous]").disabled = cursor <= first;
      grid.querySelector("[data-day-next]").disabled = cursor + pageSize > last;
      grid.querySelector("[data-day-range]").textContent =
        format.format(new Date(cursor * day)) +
        " – " +
        format.format(new Date((cursor + pageSize - 1) * day));
    });
    return true;
  }
  grids.forEach(function (grid) {
    grid
      .querySelector("[data-day-previous]")
      .addEventListener("click", function () {
        cursor -= pageSize;
        render();
      });
    grid
      .querySelector("[data-day-next]")
      .addEventListener("click", function () {
        cursor += pageSize;
        render();
      });
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(render);
      observer.observe(grid);
      observers.push(observer);
    }
  });
  let attempts = 0;
  function initialize() {
    if (disposed) return;
    if (!render() && attempts++ < 100) retryTimer = setTimeout(initialize, 100);
  }
  initialize();
}
document.addEventListener("DOMContentLoaded", initializeDayComparisons);
document.addEventListener("babybuddy:reports-ready", initializeDayComparisons);
