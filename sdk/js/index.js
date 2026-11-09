// The Gink API for JavaScript and TypeScript (Node 18+, Deno, Bun and browsers: it only needs fetch).
//
//   import { Gink } from "gink-ai";
//   const gink = new Gink();                                  // apiKey or process.env.GINK_API_KEY
//   const it = await gink.interactions.create({ input: "Write report.md on solar energy in my country", environment: "remote" });
//   console.log(it.output_text, it.files_changed);
//   for await (const event of gink.interactions.stream({ input: "Add this year's numbers", previous_interaction_id: it.id }))
//     console.log(event.type, event.data);                     // live: step, status, done
//
// In a browser, never put your API key in a page anyone can open: call Gink from your own server.

export const DEFAULT_BASE_URL = "https://gink-server.onrender.com/v1";

export class GinkAPIError extends Error {
  constructor(message, status = 0, code = "") {
    super(message);
    this.name = "GinkAPIError";
    this.status = status;
    this.code = code;
  }
}

// The machine's time zone and language (no location lookup): answers fit the user's own country.
function placeHeaders() {
  const h = {};
  try { const tz = Intl.DateTimeFormat().resolvedOptions().timeZone; if (tz) h["X-Gink-TZ"] = tz; } catch (e) { /* none */ }
  try { const loc = Intl.DateTimeFormat().resolvedOptions().locale; if (loc) h["X-Gink-Locale"] = loc; } catch (e) { /* none */ }
  return h;
}

function env(name) {
  try { return (typeof process !== "undefined" && process.env && process.env[name]) || ""; } catch (e) { return ""; }
}

export class Gink {
  constructor({ apiKey, baseURL, fetch: fetchImpl } = {}) {
    this.apiKey = apiKey || env("GINK_API_KEY");
    if (!this.apiKey) throw new GinkAPIError("No API key: pass { apiKey } or set GINK_API_KEY.", 401, "invalid_api_key");
    this.baseURL = (baseURL || env("GINK_BASE_URL") || DEFAULT_BASE_URL).replace(/\/+$/, "");
    this._fetch = fetchImpl || globalThis.fetch.bind(globalThis);
    this.interactions = new Interactions(this);
    this.environments = new Environments(this);
    this.schedules = new Schedules(this);
    this.webhooks = {
      secret: async () => (await this.request("GET", "/webhooks/secret")).secret,
      rotate: async () => (await this.request("POST", "/webhooks/secret/rotate")).secret,
    };
  }

  async request(method, path, { json, body, raw } = {}) {
    const headers = { Authorization: `Bearer ${this.apiKey}`, ...placeHeaders() };
    if (json !== undefined) headers["Content-Type"] = "application/json";
    let res;
    try {
      res = await this._fetch(this.baseURL + path, { method, headers, body: json !== undefined ? JSON.stringify(json) : body });
    } catch (err) {
      throw new GinkAPIError(`Couldn't reach Gink (${err && err.name ? err.name : "network error"}).`, 0, "network");
    }
    if (!res.ok) throw await toError(res);
    return raw ? res : res.json();
  }

  async chat(message, { model, system, ...extra } = {}) {
    const messages = Array.isArray(message) ? message
      : [...(system ? [{ role: "system", content: system }] : []), { role: "user", content: String(message) }];
    const data = await this.request("POST", "/chat/completions", { json: { messages, ...(model ? { model } : {}), ...extra } });
    return (((data.choices || [])[0] || {}).message || {}).content || "";
  }

  search(question) { return this.chat(question, { model: "gink-search" }); }

  // { idea, subject, style, aspect_ratio, photo } -- photo: Uint8Array or base64, to start from someone's own photo
  async image(prompt = "", { idea, subject, style, aspect_ratio, photo } = {}) {
    const body = { prompt };
    if (idea) Object.assign(body, { idea, subject: subject || prompt });
    if (style) body.style = style;
    if (aspect_ratio) body.aspect_ratio = aspect_ratio;
    if (photo) body.photo = typeof photo === "string" ? photo : bytesToBase64(photo);
    const data = await this.request("POST", "/images/generations", { json: body });
    return base64ToBytes(data.data[0].b64_json);
  }

  imageIdeas() { return this.request("GET", "/images/ideas"); }

  async models() { return ((await this.request("GET", "/models")).data || []).map((m) => m.id); }
}

async function toError(res) {
  let message = `HTTP ${res.status}`, code = "";
  try {
    const j = await res.json();
    const e = j.error || {};
    message = e.message || j.detail || message;
    code = e.code || "";
  } catch (e) { /* not JSON */ }
  return new GinkAPIError(String(message), res.status, code);
}

function bytesToBase64(bytes) {
  if (typeof Buffer !== "undefined") return Buffer.from(bytes).toString("base64");
  let bin = ""; for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function base64ToBytes(b64) {
  if (typeof Buffer !== "undefined") return new Uint8Array(Buffer.from(b64, "base64"));
  const bin = atob(b64), out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function body(params, extra = {}) {
  const b = { agent: params.agent || "gink-agent", input: params.input, max_steps: params.max_steps ?? 15, ...extra };
  if (params.previous_interaction_id) b.previous_interaction_id = params.previous_interaction_id;
  else b.environment = params.environment || "remote";
  if (params.tools) b.tools = params.tools;
  if (params.background) b.background = true;
  if (params.webhook_url) b.webhook_url = params.webhook_url;
  return b;
}

class Interactions {
  constructor(client) { this.c = client; }

  create(params) { return this.c.request("POST", "/interactions", { json: body(params) }); }

  async *stream(params) {
    const res = await this.c.request("POST", "/interactions", { json: body(params, { stream: true }), raw: true });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "", type = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).replace(/\r$/, "");
        buf = buf.slice(nl + 1);
        if (line.startsWith("event: ")) type = line.slice(7).trim();
        else if (line.startsWith("data: ")) yield { type, data: JSON.parse(line.slice(6)) };
      }
    }
  }

  get(id) { return this.c.request("GET", `/interactions/${encodeURIComponent(id)}`); }
  cancel(id) { return this.c.request("POST", `/interactions/${encodeURIComponent(id)}/cancel`); }

  async wait(id, { every = 1500, timeout = 1800000 } = {}) {
    const end = Date.now() + timeout;
    for (;;) {
      const it = await this.get(id);
      if (it.status !== "running" || Date.now() > end) return it;
      await new Promise((r) => setTimeout(r, every));
    }
  }
}

export class Environment {
  constructor(data, client) { Object.assign(this, data); Object.defineProperty(this, "_c", { value: client }); }
  path(p) { return `/environments/${encodeURIComponent(this.id)}/files/${p.split("/").map(encodeURIComponent).join("/")}`; }
  async upload(path, content) {
    Object.assign(this, await this._c.request("PUT", this.path(path), { body: content }));
    return this;
  }
  async download(path) { return new Uint8Array(await (await this._c.request("GET", this.path(path), { raw: true })).arrayBuffer()); }
  async text(path) { return new TextDecoder().decode(await this.download(path)); }
  async refresh() { Object.assign(this, await this._c.request("GET", `/environments/${encodeURIComponent(this.id)}`)); return this; }
  delete() { return this._c.request("DELETE", `/environments/${encodeURIComponent(this.id)}`); }
}

class Environments {
  constructor(client) { this.c = client; }
  async create({ name = "Agent environment" } = {}) { return new Environment(await this.c.request("POST", "/environments", { json: { name } }), this.c); }
  async list() { return ((await this.c.request("GET", "/environments")).data || []).map((e) => new Environment(e, this.c)); }
  async get(id) { return new Environment(await this.c.request("GET", `/environments/${encodeURIComponent(id)}`), this.c); }
}

// Scheduled agents: gink.schedules.create({ input: "Update report.md with today's news", every: "daily", at: "08:00" })
class Schedules {
  constructor(client) { this.c = client; }
  create({ input, every = "daily", at = "08:00", timezone, environment = "remote", tools, webhook_url } = {}) {
    const body = { input, every, at, environment };
    if (webhook_url) body.webhook_url = webhook_url;
    if (timezone) body.timezone = timezone;
    if (tools) body.tools = tools;
    return this.c.request("POST", "/schedules", { json: body });
  }
  async list() { return (await this.c.request("GET", "/schedules")).data || []; }
  run(id) { return this.c.request("POST", `/schedules/${encodeURIComponent(id)}/run`); }
  pause(id) { return this.c.request("PATCH", `/schedules/${encodeURIComponent(id)}`, { json: { enabled: false } }); }
  resume(id) { return this.c.request("PATCH", `/schedules/${encodeURIComponent(id)}`, { json: { enabled: true } }); }
  delete(id) { return this.c.request("DELETE", `/schedules/${encodeURIComponent(id)}`); }
}

// Check a webhook really came from Gink, then get its JSON. body: the raw request body (string, exactly as received);
// signature: the Gink-Signature header; secret: from gink.webhooks.secret(). Uses Web Crypto (Node 18+, Deno, Bun).
export async function verifyWebhook(body, signature, secret, { tolerance = 300 } = {}) {
  const parts = Object.fromEntries(String(signature || "").split(",").map((p) => p.split("=")).filter((p) => p.length === 2));
  const ts = parseInt(parts.t, 10);
  if (!ts) throw new GinkAPIError("Bad Gink-Signature header.", 400, "bad_signature");
  if (Math.abs(Date.now() / 1000 - ts) > tolerance) throw new GinkAPIError("The webhook is too old (or the clocks differ).", 400, "stale_signature");
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const mac = new Uint8Array(await crypto.subtle.sign("HMAC", key, enc.encode(`${ts}.${body}`)));
  const hex = Array.from(mac, (b) => b.toString(16).padStart(2, "0")).join("");
  let diff = hex.length ^ String(parts.v1 || "").length;
  for (let i = 0; i < hex.length; i++) diff |= hex.charCodeAt(i) ^ String(parts.v1 || "").charCodeAt(i);
  if (diff) throw new GinkAPIError("The webhook's signature doesn't match.", 400, "bad_signature");
  return JSON.parse(body);
}

export default Gink;
