import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
const source = fs.readFileSync(
  "babybuddy/static_src/js/offline_sync.js",
  "utf8",
);
const clone = (v) => (v === undefined ? undefined : structuredClone(v));
async function setup() {
  const rows = new Map([
    [
      "profile",
      { id: "profile", user: 1, children: [], activities: [], history: [] },
    ],
  ]);
  const events = new Map();
  const intervals = [];
  const posts = [];
  let now = 1000000000,
    mode = "ok",
    owner = 1,
    reads = 0,
    blocker = null;
  const db = {
    transaction() {
      const tx = {
        objectStore: () => ({
          get: (id) => ({ result: clone(rows.get(id)) }),
          getAll: () => ({ result: clone([...rows.values()]) }),
          put: (value) => {
            rows.set(value.id, clone(value));
            return { result: value.id };
          },
          delete: (id) => {
            rows.delete(id);
            return {};
          },
          clear: () => {
            rows.clear();
            return {};
          },
        }),
      };
      setTimeout(() => tx.oncomplete?.(), 0);
      return tx;
    },
  };
  const listen = (name, fn) => {
    const list = events.get(name) || [];
    list.push(fn);
    events.set(name, list);
  };
  const config = {
    dataset: { scope: "/babybuddy/", context: "/context", sync: "/sync" },
  };
  const document = {
    hidden: false,
    getElementById: (id) => (id === "offline-log" ? config : null),
    addEventListener: listen,
  };
  const context = {
    document,
    indexedDB: {
      open() {
        const r = { result: db };
        setTimeout(() => r.onsuccess(), 0);
        return r;
      },
    },
    navigator: {},
    AbortController,
    setTimeout,
    clearTimeout,
    setInterval: (fn, delay) => intervals.push({ fn, delay }),
    Date: class extends Date {
      static now() {
        return now;
      }
    },
    CustomEvent: class {
      constructor(type, { detail }) {
        this.type = type;
        this.detail = detail;
      }
    },
    addEventListener: listen,
    dispatchEvent: (event) =>
      (events.get(event.type) || []).forEach((fn) => fn(event)),
    fetch: async (url, options) => {
      if (mode === "offline") throw new Error("unreachable");
      if (url === "/context") {
        reads++;
        return {
          ok: true,
          json: async () => ({
            user: owner,
            csrf: "temporary",
            history: [{ key: "note:1" }],
            children: [],
            activities: [],
          }),
        };
      }
      posts.push(JSON.parse(options.body));
      if (blocker) {
        const wait = blocker;
        blocker = null;
        await wait;
      }
      if (mode === "lost-response")
        throw new Error("lost response after server saved");
      if (mode === "invalid")
        return {
          ok: false,
          status: 400,
          json: async () => ({ time: ["Invalid"] }),
        };
      return { ok: true, json: async () => ({ id: 123, activity: "note" }) };
    },
  };
  context.window = context;
  vm.runInNewContext(source, context);
  const api = await context.BabyBuddyOffline.ready;
  const queue = () =>
    rows.set("stable-id", {
      id: "stable-id",
      kind: "entry",
      user: 1,
      activity: "note",
      entry: { note: "Example" },
    });
  return {
    api,
    rows,
    queue,
    posts,
    intervals,
    document,
    events,
    setMode: (v) => (mode = v),
    setOwner: (v) => (owner = v),
    advance: (ms) => (now += ms),
    reads: () => reads,
    holdNextPost: (promise) => {
      blocker = promise;
    },
  };
}
test("offline entries survive until confirmed; retries retain their deduplication key", async () => {
  const s = await setup();
  s.queue();
  s.setMode("offline");
  await s.api.sync();
  assert.ok(s.rows.has("stable-id"));
  s.setMode("lost-response");
  await s.api.sync();
  assert.ok(s.rows.has("stable-id"));
  s.setMode("ok");
  await s.api.sync();
  assert.ok(!s.rows.has("stable-id"));
  assert.equal(s.posts.length, 2);
  assert.equal(s.posts[0].key, s.posts[1].key);
  assert.equal(s.rows.get("profile").history.length, 1);
  assert.equal(s.rows.get("profile").csrf, undefined);
});
test("five-minute poll detects server recovery even without a browser online event", async () => {
  const s = await setup();
  s.queue();
  s.setMode("offline");
  await s.api.sync();
  s.setMode("ok");
  assert.equal(s.intervals[0].delay, 300000);
  await s.api.sync(false);
  assert.ok(s.rows.has("stable-id"));
  s.advance(300000);
  s.intervals[0].fn();
  await s.api.sync(false);
  assert.ok(!s.rows.has("stable-id"));
  const before = s.reads();
  s.document.hidden = true;
  s.advance(300000);
  s.intervals[0].fn();
  assert.equal(s.reads(), before);
});
test("wrong account cannot send queued entries or overwrite cached history", async () => {
  const s = await setup();
  s.queue();
  s.setOwner(2);
  await s.api.sync();
  assert.equal(s.posts.length, 0);
  assert.equal(s.rows.get("profile").user, 1);
  assert.ok(s.rows.has("stable-id"));
});
test("rejected entries remain available for correction and clear removes device data", async () => {
  const s = await setup();
  s.queue();
  s.setMode("invalid");
  await s.api.sync();
  assert.equal(s.rows.get("stable-id").status, 400);
  assert.ok(s.rows.get("stable-id").error.includes("Invalid"));
  await s.api.clear();
  assert.equal(s.rows.size, 0);
});
test("reconnect and returning to the app trigger a sync", async () => {
  const s = await setup();
  for (const name of ["online", "pageshow", "focus", "visibilitychange"]) {
    s.queue();
    s.events.get(name)[0]();
    await s.api.sync();
    assert.ok(!s.rows.has("stable-id"), name);
  }
});

test("clearing a device does not upload an unsent queue first", async () => {
  const s = await setup();
  s.queue();
  await s.api.clear();
  assert.equal(s.posts.length, 0);
  assert.equal(s.rows.size, 0);
});

test("an entry added during a sync is included before that sync finishes", async () => {
  const s = await setup();
  s.queue();
  let release;
  s.holdNextPost(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  const first = s.api.sync();
  while (!s.posts.length)
    await new Promise((resolve) => setTimeout(resolve, 1));
  await s.api.enqueue({
    id: "next-id",
    kind: "entry",
    user: 1,
    activity: "note",
    entry: { note: "Second" },
  });
  const joined = s.api.sync();
  release();
  await Promise.all([first, joined]);
  assert.deepEqual(
    s.posts.map((p) => p.key),
    ["stable-id", "next-id"],
  );
  assert.equal((await s.api.entries(1)).length, 0);
});
