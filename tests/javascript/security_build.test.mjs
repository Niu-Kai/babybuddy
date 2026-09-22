import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import AdmZip from "adm-zip";
import { extractFontello, updateFontello } from "../../scripts/fontello.mjs";

// Network is mocked: the audit never uploads an icon configuration to Fontello.
test("icon updates retain fonts, CSS and config with safe paths", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "babybuddy-font-test-"));
  const archive = new AdmZip();
  archive.addFile("fontello-123/font/icons.woff2", Buffer.from("font"));
  archive.addFile("fontello-123/css/icons.css", Buffer.from(".icon {}"));
  archive.addFile("fontello-123/config.json", Buffer.from("{}"));
  try {
    await extractFontello(archive.toBuffer(), root);
    assert.equal(
      await readFile(path.join(root, "font/icons.woff2"), "utf8"),
      "font",
    );
    assert.equal(
      await readFile(path.join(root, "css/icons.css"), "utf8"),
      ".icon {}",
    );
  } finally {
    assert.ok(
      path.resolve(root).startsWith(path.resolve(os.tmpdir()) + path.sep),
    );
    await rm(root, { recursive: true, force: true });
  }
});

test("icon updater rejects a remote session with path traversal", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => ({
    ok: true,
    text: async () => "../../private",
  });
  try {
    await assert.rejects(
      updateFontello("babybuddy/static_src/fontello/config.json", "."),
      /Invalid Fontello session/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("chart bundle contains Plotly and browser-ready locale registrations", async () => {
  const bundle = await readFile(
    "babybuddy/static/babybuddy/js/graph.js",
    "utf8",
  );
  assert.match(bundle, /Plotly/);
  assert.match(bundle, /Plotly.register/);
  assert.match(bundle, /name:"fr"/);
});
