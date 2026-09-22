function initializeReportCharts(event) {
  const root =
    event && event.detail && event.detail.root ? event.detail.root : document;
  const observers = [];
  let disposed = false;
  let retryTimer;
  const cleanup = function () {
    disposed = true;
    clearTimeout(retryTimer);
    observers.forEach(function (observer) {
      observer.disconnect();
    });
  };

  const reports = root.querySelector("[data-report-charts]");
  if (!reports) return;
  reports.reportCleanup = cleanup;
  const charts = Array.from(reports.querySelectorAll(".plotly-graph-div"));
  const checkboxes = Array.from(
    reports.querySelectorAll("[data-growth-reference]"),
  );
  const initialized = new WeakSet();

  function updateReferences(chart) {
    if (!window.Plotly || !chart.data) return;
    checkboxes.forEach(function (checkbox) {
      chart.data.forEach(function (trace, index) {
        if (
          (trace.meta || {}).reference === checkbox.value &&
          trace.visible !== checkbox.checked
        ) {
          Plotly.restyle(chart, { visible: checkbox.checked }, [index]);
        }
      });
    });
  }
  // Bind controls before styling charts: one unfinished chart must not prevent
  // any checkbox from working. Replay the selected state once rendering finishes.
  checkboxes.forEach(function (checkbox) {
    checkbox.addEventListener("change", function () {
      charts.forEach(updateReferences);
    });
  });
  const units = reports.querySelector("[data-report-unit]");
  if (units)
    units.addEventListener("change", function () {
      units.form.requestSubmit();
    });

  function themeLayout() {
    const theme = getComputedStyle(document.documentElement);
    const foreground =
      theme.getPropertyValue("--bs-body-color").trim() || "#f1f5f9";
    const border =
      theme.getPropertyValue("--bs-border-color").trim() || "#94a3b8";
    const background =
      theme.getPropertyValue("--bs-body-bg").trim() || "#1b2430";
    const tooltipBorder =
      theme.getPropertyValue("--bs-secondary-color").trim() || border;
    return {
      "xaxis.rangeselector.visible": false,
      "title.text": "",
      "margin.t": 32,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      "font.color": foreground,
      "legend.font.color": foreground,
      "xaxis.title.font.color": foreground,
      "yaxis.title.font.color": foreground,
      "hoverlabel.bgcolor": background,
      "hoverlabel.bordercolor": tooltipBorder,
      "hoverlabel.font.color": foreground,
      "hoverlabel.font.size": 15,
      "hoverlabel.align": "left",
      "hoverlabel.namelength": -1,
      "xaxis.color": foreground,
      "yaxis.color": foreground,
      "xaxis.gridcolor": border,
      "yaxis.gridcolor": border,
      "xaxis.showline": true,
      "yaxis.showline": true,
      "xaxis.linecolor": border,
      "yaxis.linecolor": border,
    };
  }

  function initialize(chart) {
    if (initialized.has(chart)) return true;
    const current = chart._fullLayout || chart.layout;
    if (
      !window.Plotly ||
      !chart.data ||
      !current ||
      !current.xaxis ||
      typeof chart.on !== "function"
    )
      return false;
    initialized.add(chart);
    const layout = themeLayout();
    if (
      current.xaxis.type === "date" &&
      reports.dataset.rangeStart &&
      reports.dataset.rangeEnd
    ) {
      layout["xaxis.autorange"] = false;
      layout["xaxis.autorangeoptions"] = null;
      layout["xaxis.range"] = [
        reports.dataset.rangeStart,
        reports.dataset.rangeEnd + " 23:59:59.999",
      ];
    }
    const ready = Plotly.relayout(chart, layout);
    if (event && event.detail && event.detail.ready)
      event.detail.ready.push(ready);
    updateReferences(chart);
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(function () {
        Plotly.Plots.resize(chart);
      });
      observer.observe(chart.parentElement);
      observers.push(observer);
    }
    chart.on("plotly_legendclick", function (event) {
      const reference = (event.data[event.curveNumber].meta || {}).reference;
      if (!reference) return;
      const checkbox = checkboxes.find(function (input) {
        return input.value === reference;
      });
      if (checkbox) {
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
      }
      return false;
    });
    chart.on("plotly_legenddoubleclick", function (event) {
      if ((event.data[event.curveNumber].meta || {}).reference) return false;
    });
    return true;
  }
  let attempts = 0;
  function initializeReadyCharts() {
    if (disposed) return;
    const ready = charts.map(initialize);
    if (
      ready.some(function (value) {
        return !value;
      }) &&
      attempts++ < 100
    )
      retryTimer = setTimeout(initializeReadyCharts, 100);
  }
  initializeReadyCharts();
  if (window.MutationObserver) {
    const observer = new MutationObserver(function () {
      charts.forEach(function (chart) {
        if (initialized.has(chart)) Plotly.relayout(chart, themeLayout());
      });
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-bs-theme"],
    });
    observers.push(observer);
  }
}
document.addEventListener("DOMContentLoaded", initializeReportCharts);
document.addEventListener("babybuddy:reports-ready", initializeReportCharts);
