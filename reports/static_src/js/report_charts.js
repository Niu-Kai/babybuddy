document.addEventListener("DOMContentLoaded", function () {
  const reports = document.querySelector("[data-report-charts]");
  if (!reports || !window.Plotly) return;
  reports.querySelectorAll(".plotly-graph-div").forEach(function (chart) {
    const theme = getComputedStyle(document.documentElement);
    const foreground = theme.getPropertyValue("--bs-body-color").trim();
    const surface = theme.getPropertyValue("--bs-body-bg").trim();
    const border = theme.getPropertyValue("--bs-border-color").trim();
    const layout = {
      "xaxis.rangeselector.visible": false,
      "title.text": "",
      "margin.t": 32,
      paper_bgcolor: surface,
      plot_bgcolor: surface,
      "font.color": foreground,
      "xaxis.color": foreground,
      "yaxis.color": foreground,
      "xaxis.gridcolor": border,
      "yaxis.gridcolor": border,
    };
    if (reports.dataset.rangeStart && reports.dataset.rangeEnd) {
      layout["xaxis.autorange"] = false;
      layout["xaxis.autorangeoptions"] = null;
      layout["xaxis.range"] = [
        reports.dataset.rangeStart,
        reports.dataset.rangeEnd + " 23:59:59.999",
      ];
    }
    Plotly.relayout(chart, layout);
  });
});
