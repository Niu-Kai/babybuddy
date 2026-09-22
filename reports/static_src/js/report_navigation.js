document.addEventListener("DOMContentLoaded", function () {
  if (!document.querySelector("[data-report-page]") || !window.fetch) return;
  let controller;
  let generation = 0;
  let plotlyLoading;
  let displayedURL = window.location.href;
  const status = document.createElement("div");
  status.className = "report-navigation-status";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.hidden = true;
  document.body.append(status);

  function isReportURL(url) {
    return (
      url.origin === window.location.origin &&
      /\/reports(?:\/|$)/.test(url.pathname)
    );
  }
  function dispose(root) {
    root.querySelectorAll("[data-timeline-filters]").forEach(function (form) {
      if (form.periodCleanup) form.periodCleanup();
    });
    root.querySelectorAll("[data-report-charts]").forEach(function (node) {
      if (node.reportCleanup) node.reportCleanup();
    });
    root.querySelectorAll("[data-day-comparison]").forEach(function (node) {
      if (node.dayCleanup) node.dayCleanup();
    });
    if (window.Plotly)
      root.querySelectorAll(".plotly-graph-div").forEach(function (chart) {
        Plotly.purge(chart);
      });
  }
  function ensurePlotly(src) {
    if (window.Plotly) return Promise.resolve();
    if (!plotlyLoading) {
      plotlyLoading = new Promise(function (resolve, reject) {
        const script = document.createElement("script");
        script.src = src;
        script.onload = resolve;
        script.onerror = function () {
          script.remove();
          reject(new Error("Chart library unavailable"));
        };
        document.head.append(script);
      }).catch(function (error) {
        plotlyLoading = null;
        throw error;
      });
    }
    return plotlyLoading;
  }
  async function navigate(url, fromHistory) {
    const ticket = ++generation;
    if (controller) controller.abort();
    controller = new AbortController();
    const current = document.querySelector("[data-report-page]");
    let stage;
    current.setAttribute("aria-busy", "true");
    status.textContent = "Loading report…";
    status.hidden = false;
    try {
      const response = await fetch(url.href, {
        headers: { "X-Report-Partial": "1" },
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      if (ticket !== generation) return;
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) throw new Error("Report unavailable");
      const payload = await response.json();
      if (ticket !== generation) return;
      const parsed = new DOMParser().parseFromString(payload.html, "text/html");
      stage = parsed.querySelector("[data-report-page]");
      if (!stage) throw new Error("Invalid report response");
      // Only Plotly JSON is interpreted. Never execute scripts from fetched HTML.
      stage.querySelectorAll("script").forEach(function (script) {
        script.remove();
      });
      stage.classList.add("report-staging");
      stage.style.width = current.getBoundingClientRect().width + "px";
      stage.setAttribute("aria-hidden", "true");
      stage.inert = true;
      current.after(stage);
      if (payload.plots.length) await ensurePlotly(payload.plotly_url);
      if (ticket !== generation) return;
      await Promise.all(
        payload.plots.map(function (plot) {
          const chart = Array.from(
            stage.querySelectorAll(".plotly-graph-div"),
          ).find(function (node) {
            return node.id === plot.id;
          });
          if (!chart) throw new Error("Missing chart container");
          return Plotly.newPlot(chart, plot.data, plot.layout, plot.config);
        }),
      );
      if (ticket !== generation) return;
      const ready = [];
      document.dispatchEvent(
        new CustomEvent("babybuddy:reports-ready", {
          detail: { root: stage, ready: ready },
        }),
      );
      await Promise.all(ready);
      if (ticket !== generation) return;
      dispose(current);
      stage.classList.remove("report-staging");
      stage.style.removeProperty("width");
      stage.removeAttribute("aria-hidden");
      stage.inert = false;
      current.replaceWith(stage);
      const childMenu = document.querySelector(".child-view-menu");
      if (childMenu) childMenu.hidden = Boolean(payload.household_page);
      const heading = stage.querySelector("h1");
      if (heading)
        document.title = heading.textContent.trim() + " · Baby Buddy";
      if (!fromHistory)
        window.history.pushState({ report: true }, "", url.href);
      displayedURL = url.href;
      stage = null;
      status.hidden = true;
    } catch (error) {
      if (ticket !== generation || error.name === "AbortError") return;
      if (fromHistory)
        window.history.replaceState({ report: true }, "", displayedURL);
      status.textContent = "Couldn’t load the report. ";
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "btn btn-sm btn-outline-primary";
      retry.textContent = "Retry";
      retry.addEventListener("click", function () {
        navigate(url, false);
      });
      status.append(retry);
    } finally {
      if (stage) {
        dispose(stage);
        stage.remove();
      }
      if (ticket === generation) current.removeAttribute("aria-busy");
    }
  }
  document.addEventListener("click", function (event) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const link = event.target.closest("a[href]");
    if (!link || link.target || link.hasAttribute("download")) return;
    if (
      !link.closest("[data-report-page]") &&
      !link.classList.contains("nav-link")
    )
      return;
    const url = new URL(link.href, window.location.href);
    if (!isReportURL(url) || url.hash) return;
    event.preventDefault();
    navigate(url, false);
  });
  document.addEventListener("submit", function (event) {
    const form = event.target;
    if (
      !form.closest("[data-report-page]") ||
      form.method.toLowerCase() !== "get"
    )
      return;
    const url = new URL(
      form.action || window.location.href,
      window.location.href,
    );
    if (!isReportURL(url)) return;
    event.preventDefault();
    url.search = new URLSearchParams(
      new FormData(form, event.submitter),
    ).toString();
    navigate(url, false);
  });
  window.addEventListener("popstate", function () {
    const url = new URL(window.location.href);
    if (isReportURL(url)) navigate(url, true);
  });
});
