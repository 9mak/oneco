// oneco のお問い合わせ Worker。POST /api/contact だけを処理し、ほかは静的アセット（env.ASSETS）に回す。
// 流れ: フォームの値を検証 → Cloudflare Turnstile で人かどうかを確かめる → メール（Email Service の send_email バインディング）で
// 9mak.org@gmail.com に送る → 結果のページへ 303。問い合わせの中身（名前・メール・本文）はログに出さない。
// npm の依存は無い。設定は v2/ops/wrangler.jsonc、手順は v2/docs/OPERATIONS.md「お問い合わせフォーム」。

const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const MAIL_FROM = "contact@oneco.pet";
// wrangler.jsonc の destination_address と同じ。ここでも固定して、バインディングの設定を変えても宛先が広がらないようにする
const MAIL_TO = "9mak.org@gmail.com";
const MAIL_SUBJECT = "[oneco] お問い合わせ";
const MAX_BODY_BYTES = 65536;
const LIMITS = { message: 4000, page_url: 500, name: 100, reply_to: 254 };
const EMAIL_RE = /^[^\s@<>"',;()[\]\\]+@[^\s@<>"',;()[\]\\]+\.[^\s@<>"',;()[\]\\]+$/;

/** @param {string} path */
function redirect(path) {
  return new Response(null, { status: 303, headers: { Location: path } });
}

/** 画面に出す値は 1 行にそろえる（本文に偽の行を差し込ませない） */
function oneLine(v) {
  return v.replace(/[\r\n\u2028\u2029]+/g, " ").trim();
}

/** @param {FormData} form @returns {{ ok: boolean, v: Record<string, string> }} */
function readFields(form) {
  const v = {};
  for (const key of Object.keys(LIMITS)) {
    const raw = form.get(key);
    v[key] = typeof raw === "string" ? raw : "";
  }
  v.message = v.message.replace(/\r\n?/g, "\n").trim();
  for (const key of ["page_url", "name", "reply_to"]) v[key] = oneLine(v[key]);
  if (!v.message) return { ok: false, v };
  for (const [key, max] of Object.entries(LIMITS)) if (v[key].length > max) return { ok: false, v };
  if (v.reply_to && !EMAIL_RE.test(v.reply_to)) return { ok: false, v };
  if (v.page_url) {
    try {
      const u = new URL(v.page_url);
      if (u.protocol !== "https:" && u.protocol !== "http:") return { ok: false, v };
    } catch {
      return { ok: false, v };
    }
  }
  return { ok: true, v };
}

/** @param {string} host */
function allowedHost(host) {
  return host === "oneco.pet" || host.endsWith(".workers.dev");
}

async function verifyTurnstile(token, ip, env, fetchImpl) {
  if (!env.TURNSTILE_SECRET || !token) return false;
  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET, response: token });
  if (ip) body.set("remoteip", ip);
  try {
    const res = await fetchImpl(SITEVERIFY_URL, { method: "POST", body });
    if (!res.ok) return false;
    const r = await res.json();
    return r.success === true && typeof r.hostname === "string" && allowedHost(r.hostname);
  } catch {
    return false;
  }
}

function jstNow() {
  // sv-SE は「2026-11-24 15:04:05」の形で出る
  const s = new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
  }).format(new Date());
  return `${s}（日本時間）`;
}

function buildMessage(v) {
  const text = [
    `お名前: ${v.name || "（未記入）"}`,
    `返信先: ${v.reply_to || "（未記入）"}`,
    `該当ページ: ${v.page_url || "（未記入）"}`,
    `受け付け: ${jstNow()}`,
    "",
    "お問い合わせ内容:",
    v.message,
    "",
  ].join("\n");
  // 件名・from・to は固定。利用者の入力は Reply-To（検証済みのメールアドレス）と本文にしか入れない
  const msg = { from: MAIL_FROM, to: MAIL_TO, subject: MAIL_SUBJECT, text };
  if (v.reply_to) msg.replyTo = v.reply_to;
  return msg;
}

export default {
  /**
   * @param {Request} request
   * @param {{ ASSETS: { fetch: (r: Request) => Promise<Response> }, SEND_EMAIL: { send: (m: object) => Promise<unknown> }, TURNSTILE_SECRET?: string }} env
   * @param {unknown} _ctx
   * @param {typeof fetch} fetchImpl 試験で Turnstile の検証を差し替える口（Workers は 3 つしか渡さないので既定の fetch になる）
   */
  async fetch(request, env, _ctx, fetchImpl = fetch) {
    const url = new URL(request.url);
    if (url.pathname !== "/api/contact") return env.ASSETS.fetch(request);
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405, headers: { Allow: "POST" } });
    }
    // content-length が無い（chunked）送信では、この上限は効かない。Cloudflare 側の本文上限と、readFields の欄ごとの長さの検査に任せる（message 4000 字ほか）
    const len = Number(request.headers.get("content-length") || 0);
    if (len > MAX_BODY_BYTES) return redirect("/contact/error/");
    let form;
    try {
      form = await request.formData();
    } catch {
      return redirect("/contact/error/");
    }
    const { ok, v } = readFields(form);
    if (!ok) return redirect("/contact/error/");
    const token = form.get("cf-turnstile-response");
    const human = await verifyTurnstile(
      typeof token === "string" ? token : "", request.headers.get("CF-Connecting-IP"), env, fetchImpl);
    if (!human) return redirect("/contact/error/");
    try {
      await env.SEND_EMAIL.send(buildMessage(v));
    } catch (e) {
      // 中身は出さない。エラーコードだけ（Email Service のエラーは .code を持つ）
      console.error("contact: send failed", e && typeof e === "object" && "code" in e ? e.code : "unknown");
      return redirect("/contact/error/");
    }
    return redirect("/contact/sent/");
  },
};
