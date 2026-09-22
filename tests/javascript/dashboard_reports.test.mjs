import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

function element(dataset = {}) {
  return {
    dataset,
    hidden: false,
    disabled: false,
    children: [],
    listeners: {},
    classList: {
      values: new Set(),
      add(value) {
        this.values.add(value);
      },
      remove(value) {
        this.values.delete(value);
      },
      contains(value) {
        return this.values.has(value);
      },
    },
    addEventListener(name, callback) {
      this.listeners[name] = callback;
    },
    fire(name, event = {}) {
      return this.listeners[name]?.call(this, event);
    },
    appendChild(child) {
      if (child.parentElement)
        child.parentElement.children.splice(
          child.parentElement.children.indexOf(child),
          1,
        );
      this.children.push(child);
      child.parentElement = this;
    },
    insertBefore(child, target) {
      if (child === target) return;
      if (child.parentElement)
        child.parentElement.children.splice(
          child.parentElement.children.indexOf(child),
          1,
        );
      const index = target
        ? this.children.indexOf(target)
        : this.children.length;
      this.children.splice(index, 0, child);
      child.parentElement = this;
    },
    get previousElementSibling() {
      return this.parentElement.children[
        this.parentElement.children.indexOf(this) - 1
      ];
    },
    get nextElementSibling() {
      return this.parentElement.children[
        this.parentElement.children.indexOf(this) + 1
      ];
    },
    get nextSibling() {
      return this.nextElementSibling;
    },
  };
}

test("reset action survives disabling the clicked submit button", () => {
  const form = element(),
    button = { name: "action", value: "reset", disabled: false };
  let handler;
  function $(target) {
    return {
      on(name, callback) {
        handler = callback;
      },
      prop(name, value) {
        if (value === undefined) return target[name];
        target[name] = value;
        return this;
      },
      prepend() {},
    };
  }
  const source = fs.readFileSync(
    "babybuddy/static_src/js/babybuddy.js",
    "utf8",
  );
  const start = source.indexOf("(function handleFormSubmit()");
  const end = source.indexOf("})();", start) + 5;
  vm.runInNewContext(source.slice(start, end), {
    $,
    document: { createElement: () => ({}) },
  });
  handler.call(form, { originalEvent: { submitter: button } });
  assert.equal(button.disabled, true);
  assert.deepEqual(
    form.children.map((input) => [input.type, input.name, input.value]),
    [["hidden", "action", "reset"]],
  );
});

test("dashboard reorders across sections, mirrors comparisons, and saves order with CSRF", async () => {
  const document = element(),
    toolbar = element({ saveUrl: "/dashboard/customize/" });
  document.body = element();
  const start = element(),
    save = element(),
    cancel = element(),
    status = element({ error: "Save failed" });
  toolbar.querySelector = (selector) =>
    ({
      "[data-arrange-start]": start,
      "[data-arrange-save]": save,
      "[data-arrange-cancel]": cancel,
      "[data-arrange-status]": status,
      "[name=csrfmiddlewaretoken]": { value: "csrf-test" },
    })[selector];
  const grids = [element(), element(), element(), element()];
  grids.forEach((grid) => {
    const section = element();
    grid.closest = () => section;
  });
  const cells = [];
  for (let child = 0; child < 2; child++) {
    for (const [index, key] of [
      "feeding_last",
      "sleep_last",
      "statistics",
    ].entries()) {
      const cell = element({ dashboardPanel: key });
      cell.closest = () => cell;
      grids[child * 2 + (index === 2 ? 1 : 0)].appendChild(cell);
      cells.push(cell);
    }
  }
  const dashboards = [0, 1].map((index) => ({
    querySelectorAll: (selector) =>
      selector === ".dash-grid" ? grids.slice(index * 2, index * 2 + 2) : [],
  }));
  document.querySelector = (selector) =>
    selector === "[data-dashboard-arrange]" ? toolbar : grids[0];
  document.querySelectorAll = (selector) =>
    selector === ".dash" ? dashboards : grids;
  let posted,
    reloaded = false;
  vm.runInNewContext(
    fs.readFileSync("dashboard/static_src/js/arrange.js", "utf8"),
    {
      document,
      FormData,
      window: {
        location: {
          reload() {
            reloaded = true;
          },
        },
      },
      fetch: async (url, request) => {
        posted = request.body;
        return { ok: true, json: async () => ({ saved: true }) };
      },
    },
  );
  document.fire("DOMContentLoaded");
  start.fire("click");
  assert.equal(grids[0].children.length, 3);
  const button = {
    dataset: { panelMove: "-1" },
    closest: () => cells[2],
    focus() {},
  };
  document.fire("click", { target: { closest: () => button } });
  const expected = ["feeding_last", "statistics", "sleep_last"];
  assert.deepEqual(
    grids[0].children.map((cell) => cell.dataset.dashboardPanel),
    expected,
  );
  assert.deepEqual(
    grids[2].children.map((cell) => cell.dataset.dashboardPanel),
    expected,
  );
  // A drag moves the final panel ahead of the first one, in both child views.
  const handle = { matches: () => true, closest: () => cells[1] };
  document.fire("dragstart", {
    target: handle,
    dataTransfer: { setData() {}, setDragImage() {} },
  });
  document.fire("drop", {
    target: { closest: () => cells[0] },
    preventDefault() {},
  });
  document.fire("dragend");
  assert.deepEqual(
    grids[0].children.map((cell) => cell.dataset.dashboardPanel),
    ["sleep_last", "feeding_last", "statistics"],
  );
  await save.fire("click");
  assert.deepEqual(posted.getAll("order"), [
    "sleep_last",
    "feeding_last",
    "statistics",
  ]);
  assert.equal(posted.get("csrfmiddlewaretoken"), "csrf-test");
  assert.equal(reloaded, true);
});

test("growth reference toggles update each child without applying date bounds to age axes", () => {
  const document = element(),
    reports = element({ rangeStart: "2024-01-01", rangeEnd: "2024-01-31" });
  const check = element();
  check.value = "girl";
  check.checked = true;
  const units = element();
  let submitted = false;
  units.form = {
    requestSubmit() {
      submitted = true;
    },
  };
  const charts = [0, 1].map(() => ({
    data: [{ name: "Child" }, { meta: { reference: "girl" }, visible: true }],
    layout: { xaxis: { type: "linear" } },
    on() {},
  }));
  const layouts = [],
    updates = [];
  reports.querySelectorAll = (selector) =>
    selector === ".plotly-graph-div" ? charts : [check];
  reports.querySelector = () => units;
  document.querySelector = () => reports;
  const Plotly = {
    relayout(chart, layout) {
      layouts.push(layout);
    },
    restyle(chart, update, indices) {
      updates.push([update.visible, indices[0]]);
    },
  };
  vm.runInNewContext(
    fs.readFileSync("reports/static_src/js/report_charts.js", "utf8"),
    {
      document,
      window: { Plotly },
      Plotly,
      getComputedStyle: () => ({ getPropertyValue: () => "#123456" }),
    },
  );
  document.fire("DOMContentLoaded");
  assert.ok(layouts.every((layout) => !Object.hasOwn(layout, "xaxis.range")));
  check.checked = false;
  check.fire("change");
  assert.deepEqual(updates, [
    [false, 1],
    [false, 1],
  ]);
  units.fire("change");
  assert.equal(submitted, true);
});

test("growth checkboxes work when chart layout initializes after the controls", () => {
  const document = element(),
    reports = element(),
    checkbox = element();
  checkbox.value = "boy";
  checkbox.checked = true;
  const chart = {},
    timers = [],
    updates = [];
  reports.querySelectorAll = (selector) =>
    selector === ".plotly-graph-div" ? [chart] : [checkbox];
  reports.querySelector = () => null;
  document.querySelector = () => reports;
  const Plotly = {
    relayout() {},
    restyle(chart, state, indices) {
      updates.push([state.visible, indices[0]]);
      chart.data[indices[0]].visible = state.visible;
    },
  };
  vm.runInNewContext(
    fs.readFileSync("reports/static_src/js/report_charts.js", "utf8"),
    {
      document,
      window: { Plotly },
      Plotly,
      setTimeout: (callback) => timers.push(callback),
      getComputedStyle: () => ({ getPropertyValue: () => "#123456" }),
    },
  );
  document.fire("DOMContentLoaded");
  assert.equal(typeof checkbox.listeners.change, "function");
  checkbox.checked = false;
  checkbox.fire("change");
  assert.equal(updates.length, 0);
  chart.data = [{ meta: { reference: "boy" }, visible: true }];
  chart.layout = { xaxis: { type: "linear" } };
  chart.on = () => {};
  timers.shift()();
  assert.deepEqual(updates, [[false, 0]]);
  checkbox.checked = true;
  checkbox.fire("change");
  assert.deepEqual(updates, [
    [false, 0],
    [true, 0],
  ]);
});

test("static service worker fetches fresh controls and falls back to cached assets offline", async () => {
  const callbacks = {},
    cached = { version: "old" },
    fresh = {
      ok: true,
      version: "new",
      clone() {
        return this;
      },
    };
  const cache = { match: async () => cached, put: async () => {} };
  let offline = false;
  const context = {
    self: {
      location: { origin: "http://localhost" },
      addEventListener(name, handler) {
        callbacks[name] = handler;
      },
    },
    URL,
    Response,
    caches: { open: async () => cache },
    fetch: async () => {
      if (offline) throw new Error("offline");
      return fresh;
    },
  };
  vm.runInNewContext(
    fs.readFileSync("babybuddy/templates/babybuddy/sw.js", "utf8"),
    context,
  );
  async function request() {
    let response;
    callbacks.fetch({
      request: { method: "GET", url: "http://localhost/static/app.js" },
      respondWith(promise) {
        response = promise;
      },
    });
    return response;
  }
  assert.equal((await request()).version, "new");
  offline = true;
  assert.equal((await request()).version, "old");
});

test("day comparison pages children together and keeps axes inside the viewport", () => {
  const updates = [];
  const grids = [0, 1].map(() => {
    const buttons = {
      "[data-day-previous]": element(),
      "[data-day-next]": element(),
      "[data-day-controls]": element(),
      "[data-day-range]": element(),
    };
    const chart = {
      _fullLayout: {},
      layout: { annotations: [{ x: 0 }, { x: 5 }] },
    };
    return {
      dataset: { firstDay: "2026-09-13", dayCount: "7", dayWidth: "180" },
      clientWidth: 720,
      querySelector(selector) {
        return selector === ".plotly-graph-div" ? chart : buttons[selector];
      },
      buttons,
    };
  });
  const plotly = {
    relayout(chart, update) {
      updates.push(update);
    },
  };
  vm.runInNewContext(
    fs.readFileSync("reports/static_src/js/day_comparison.js", "utf8"),
    {
      document: {
        querySelectorAll() {
          return grids;
        },
        addEventListener(event, callback) {
          if (event === "DOMContentLoaded") callback();
        },
      },
      window: { Plotly: plotly },
      Plotly: plotly,
      Intl,
      Date,
      setTimeout,
    },
  );
  assert.equal(updates.length, 2);
  assert.deepEqual(Array.from(updates[0]["xaxis.range"]), [-0.5, 2.5]);
  assert.equal(updates[0].annotations[1].visible, false);
  grids[0].buttons["[data-day-next]"].fire("click");
  assert.deepEqual(Array.from(updates[2]["xaxis.range"]), [2.5, 5.5]);
  assert.deepEqual(Array.from(updates[3]["xaxis.range"]), [2.5, 5.5]);
  grids[1].buttons["[data-day-next]"].fire("click");
  assert.equal(grids[0].buttons["[data-day-next]"].disabled, true);
  grids[1].buttons["[data-day-previous]"].fire("click");
  assert.equal(grids[0].buttons["[data-day-next]"].disabled, false);
});
