import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

test("hospital checklist posts to its page when the action field shadows form.action", async () => {
  let initialize, change, posted;
  const checkbox = {
    checked: true,
    disabled: false,
    addEventListener: (event, callback) => {
      change = callback;
    },
  };
  const packed = { value: "0" };
  const counter = {};
  const error = {};
  const form = {
    action: { value: "toggle-item" },
    getAttribute: () => null,
    querySelector: (selector) =>
      selector === '[type="checkbox"]' ? checkbox : packed,
    addEventListener() {},
  };
  class FormData {
    values = new Map();
    set(key, value) {
      this.values.set(key, value);
    }
    get(key) {
      return this.values.get(key);
    }
  }
  vm.runInNewContext(
    fs.readFileSync("core/static_src/js/prebirth.js", "utf8"),
    {
      FormData,
      window: { location: { href: "https://example.test/before-birth/" } },
      document: {
        addEventListener: (event, callback) => {
          initialize = callback;
        },
        querySelector: (selector) => {
          if (selector === "[data-contractions]") return null;
          if (selector === "[data-packing-error]") return error;
          if (selector === "[data-packing-count]") return counter;
          return { value: "csrf" };
        },
        querySelectorAll: () => [form],
      },
      fetch: async (url, request) => {
        posted = { url, request };
        return { ok: true, json: async () => ({ packed: 1, total: 17 }) };
      },
    },
  );
  initialize();
  await change();
  assert.equal(posted.url, "https://example.test/before-birth/");
  assert.equal(posted.request.method, "POST");
  assert.equal(posted.request.body.get("packed"), "1");
  assert.equal(counter.textContent, "1 / 17");
  assert.equal(checkbox.disabled, false);
  assert.equal(error.hidden, true);
});
