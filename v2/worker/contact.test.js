// お問い合わせ Worker（contact.js）の試験。`node --test v2/worker/` で動く（依存なし）。
// Turnstile の検証（fetch）とメール送信（env.SEND_EMAIL）は偽物に差し替える。
import { test } from "node:test";
import assert from "node:assert/strict";
import worker from "./contact.js";

const VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

function makeEnv({ turnstile = { success: true, hostname: "oneco.pet" }, sendError = null, secret = "sekret" } = {}) {
  const calls = { assets: [], verify: [], send: [] };
  const env = {
    TURNSTILE_SECRET: secret,
    ASSETS: { fetch: async (req) => { calls.assets.push(new URL(req.url).pathname); return new Response("asset", { status: 200 }); } },
    SEND_EMAIL: { send: async (msg) => { calls.send.push(msg); if (sendError) throw sendError; return { messageId: "m1" }; } },
  };
  const fetchImpl = async (url, init) => {
    calls.verify.push({ url: String(url), body: new URLSearchParams(String(init.body)) });
    return new Response(JSON.stringify(turnstile), { status: 200, headers: { "content-type": "application/json" } });
  };
  return { env, calls, fetchImpl };
}

function post(fields, { multipart = false, headers = {} } = {}) {
  const f = { message: "犬の写真について", "cf-turnstile-response": "tok", ...fields };
  let body;
  if (multipart) {
    body = new FormData();
    for (const [k, v] of Object.entries(f)) if (v !== undefined) body.append(k, v);
  } else {
    body = new URLSearchParams();
    for (const [k, v] of Object.entries(f)) if (v !== undefined) body.set(k, v);
  }
  return new Request("https://oneco.pet/api/contact", { method: "POST", body, headers: { "CF-Connecting-IP": "203.0.113.9", ...headers } });
}

const run = (req, ctx) => worker.fetch(req, ctx.env, {}, ctx.fetchImpl);
const loc = (res) => res.headers.get("location");

test("正常: メールを送って /contact/sent/ へ 303", async () => {
  const ctx = makeEnv();
  const res = await run(post({ name: "山田", reply_to: "a@example.com", page_url: "https://oneco.pet/animals/x/", message: "訂正のお願い" }), ctx);
  assert.equal(res.status, 303);
  assert.equal(loc(res), "/contact/sent/");
  assert.equal(ctx.calls.send.length, 1);
  const m = ctx.calls.send[0];
  assert.equal(m.from, "contact@oneco.pet");
  assert.equal(m.to, "9mak.org@gmail.com");
  assert.equal(m.subject, "[oneco] お問い合わせ");
  assert.equal(m.replyTo, "a@example.com");
  for (const s of ["山田", "a@example.com", "https://oneco.pet/animals/x/", "訂正のお願い"]) assert.ok(m.text.includes(s), s);
  assert.match(m.text, /\d{4}-\d{2}-\d{2} \d{2}:\d{2}.*日本時間|JST/);
});

test("Turnstile の検証に secret・トークン・IP を渡す", async () => {
  const ctx = makeEnv();
  await run(post({}), ctx);
  assert.equal(ctx.calls.verify.length, 1);
  assert.equal(ctx.calls.verify[0].url, VERIFY_URL);
  assert.equal(ctx.calls.verify[0].body.get("secret"), "sekret");
  assert.equal(ctx.calls.verify[0].body.get("response"), "tok");
  assert.equal(ctx.calls.verify[0].body.get("remoteip"), "203.0.113.9");
});

test("multipart/form-data でも読める。reply_to が無ければ replyTo を付けない", async () => {
  const ctx = makeEnv();
  const res = await run(post({}, { multipart: true }), ctx);
  assert.equal(loc(res), "/contact/sent/");
  assert.equal(ctx.calls.send[0].replyTo, undefined);
});

test("*.workers.dev のホスト名も通す", async () => {
  const ctx = makeEnv({ turnstile: { success: true, hostname: "oneco.example.workers.dev" } });
  assert.equal(loc(await run(post({}), ctx)), "/contact/sent/");
});

for (const [label, fields] of [
  ["message が空", { message: "" }],
  ["message が空白だけ", { message: "  \n " }],
  ["message が長すぎる", { message: "あ".repeat(4001) }],
  ["page_url が長すぎる", { page_url: "https://oneco.pet/" + "a".repeat(500) }],
  ["name が長すぎる", { name: "あ".repeat(101) }],
  ["reply_to が長すぎる", { reply_to: "a".repeat(250) + "@example.com" }],
  ["reply_to の形が違う", { reply_to: "not-an-email" }],
  ["reply_to に改行", { reply_to: "a@example.com\r\nBcc: x@example.com" }],
  ["page_url の形が違う", { page_url: "oneco.pet/about" }],
  ["page_url が http(s) でない", { page_url: "javascript:alert(1)" }],
]) {
  test(`入力が不正（${label}）: 送らず /contact/error/ へ 303`, async () => {
    const ctx = makeEnv();
    const res = await run(post(fields), ctx);
    assert.equal(res.status, 303);
    assert.equal(loc(res), "/contact/error/");
    assert.equal(ctx.calls.send.length, 0);
  });
}

test("message の長さは 4000 ちょうどなら通る", async () => {
  const ctx = makeEnv();
  assert.equal(loc(await run(post({ message: "あ".repeat(4000) }), ctx)), "/contact/sent/");
});

for (const [label, turnstile] of [
  ["success でない", { success: false, "error-codes": ["invalid-input-response"] }],
  ["hostname が違う", { success: true, hostname: "evil.example.com" }],
  ["hostname が無い", { success: true }],
  ["oneco.pet に見せかけたホスト", { success: true, hostname: "oneco.pet.evil.com" }],
]) {
  test(`Turnstile の失敗（${label}）: 送らず error`, async () => {
    const ctx = makeEnv({ turnstile });
    const res = await run(post({}), ctx);
    assert.equal(loc(res), "/contact/error/");
    assert.equal(ctx.calls.send.length, 0);
  });
}

test("Turnstile のトークンが無ければ検証せず error", async () => {
  const ctx = makeEnv();
  const res = await run(post({ "cf-turnstile-response": undefined }), ctx);
  assert.equal(loc(res), "/contact/error/");
  assert.equal(ctx.calls.send.length, 0);
});

test("TURNSTILE_SECRET が無ければ error（送らない）", async () => {
  const ctx = makeEnv({ secret: null });
  const res = await run(post({}), ctx);
  assert.equal(loc(res), "/contact/error/");
  assert.equal(ctx.calls.send.length, 0);
  assert.equal(ctx.calls.verify.length, 0);
});

test("Turnstile の検証が落ちても error", async () => {
  const ctx = makeEnv();
  ctx.fetchImpl = async () => { throw new Error("network"); };
  assert.equal(loc(await run(post({}), ctx)), "/contact/error/");
  assert.equal(ctx.calls.send.length, 0);
});

test("メール送信の失敗: /contact/error/ へ 303。中身をログに出さない", async () => {
  const ctx = makeEnv({ sendError: Object.assign(new Error("boom"), { code: "E_DELIVERY_FAILED" }) });
  const logged = [];
  const orig = { log: console.log, error: console.error, warn: console.warn };
  console.log = console.error = console.warn = (...a) => logged.push(a.join(" "));
  let res;
  try { res = await run(post({ message: "秘密の内容ABC", name: "山田太郎" }), ctx); } finally { Object.assign(console, orig); }
  assert.equal(loc(res), "/contact/error/");
  const all = logged.join("\n");
  assert.ok(!all.includes("秘密の内容ABC") && !all.includes("山田太郎"));
});

test("ヘッダーに改行を差し込めない（件名は固定、replyTo は検証済み、本文の改行は本文のまま）", async () => {
  const ctx = makeEnv();
  await run(post({ name: "x\r\nBcc: evil@example.com", message: "a\r\nBcc: evil@example.com" }), ctx);
  const m = ctx.calls.send[0];
  assert.equal(m.subject, "[oneco] お問い合わせ");
  assert.ok(!/[\r\n]/.test(m.subject) && !/[\r\n]/.test(m.from) && !/[\r\n]/.test(m.to));
  assert.equal(m.headers, undefined);
});

test("GET /api/contact は 405", async () => {
  const ctx = makeEnv();
  const res = await run(new Request("https://oneco.pet/api/contact"), ctx);
  assert.equal(res.status, 405);
  assert.equal(res.headers.get("allow"), "POST");
  assert.equal(ctx.calls.assets.length, 0);
});

test("POST 以外のパスは ASSETS に回す", async () => {
  const ctx = makeEnv();
  for (const [method, path] of [["GET", "/"], ["GET", "/contact/"], ["POST", "/other"], ["GET", "/api/other"]]) {
    const res = await run(new Request(`https://oneco.pet${path}`, { method, body: method === "POST" ? "x" : undefined }), ctx);
    assert.equal(res.status, 200);
    assert.equal(await res.text(), "asset");
  }
  assert.deepEqual(ctx.calls.assets, ["/", "/contact/", "/other", "/api/other"]);
  assert.equal(ctx.calls.send.length, 0);
});
