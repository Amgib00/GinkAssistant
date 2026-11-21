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

// The clock's offset from UTC, like "+01:00" (no time zone name, no region).
export function utcOffset() {
  const m = -new Date().getTimezoneOffset(), a = Math.abs(m);
  return (m >= 0 ? "+" : "-") + String(Math.floor(a / 60)).padStart(2, "0") + ":" + String(a % 60).padStart(2, "0");
}

// The machine's time zone and language (no location lookup): answers fit the user's own country.
// location: false (or GINK_LOCATION=off) -- like Settings > Privacy > "Location metadata" off: the clock only.
function placeHeaders(location) {
  if (location === undefined || location === null) location = !/^(off|0|false|no)$/i.test(env("GINK_LOCATION"));
  if (!location) return { "X-Gink-Location": "off", "X-Gink-UTC-Offset": utcOffset() };
  const h = {};
  try { const tz = Intl.DateTimeFormat().resolvedOptions().timeZone; if (tz) h["X-Gink-TZ"] = tz; } catch (e) { /* none */ }
  try { const loc = Intl.DateTimeFormat().resolvedOptions().locale; if (loc) h["X-Gink-Locale"] = loc; } catch (e) { /* none */ }
  return h;
}

function env(name) {
  try { return (typeof process !== "undefined" && process.env && process.env[name]) || ""; } catch (e) { return ""; }
}

export class Gink {
  constructor({ apiKey, baseURL, fetch: fetchImpl, location } = {}) {
    this.location = location;                          // false: no location metadata (city/region), the clock only
    this.apiKey = apiKey || env("GINK_API_KEY");
    if (!this.apiKey) throw new GinkAPIError("No API key: pass { apiKey } or set GINK_API_KEY.", 401, "invalid_api_key");
    this.baseURL = (baseURL || env("GINK_BASE_URL") || DEFAULT_BASE_URL).replace(/\/+$/, "");
    this._fetch = fetchImpl || globalThis.fetch.bind(globalThis);
    this.interactions = new Interactions(this);
    this.environments = new Environments(this);
    this.schedules = new Schedules(this);
    this.memories = {                                  // what Gink remembers about you (the same as your apps)
      list: async () => (await this.request("GET", "/memories")).data || [],
      add: (text) => this.request("POST", "/memories", { json: { text } }),
      forget: (id) => this.request("DELETE", `/memories/${encodeURIComponent(id)}`),
      suggest: async (text, { sensitive = false } = {}) =>
        (await this.request("POST", "/memories/suggest", { json: { text, sensitive } })).fact || null,
      // "Generate memory from chats": the lasting facts in a conversation (a messages list), at most 5, saved unless save: false
      generate: async (messages, { save = true, sensitive = false } = {}) =>
        (await this.request("POST", "/memories/generate", { json: { messages, save, sensitive } })).data || [],
      // "Import memory from other AI providers": ask your other assistant importPrompt(), then pass its answer to import()
      importPrompt: async () => (await this.request("GET", "/memories/import-prompt")).prompt || "",
      import: (text, { sensitive = false } = {}) => this.request("POST", "/memories/import", { json: { text: String(text), sensitive } }),
    };
    this.workspace = {                                 // your workspace; admins: healthcare mode's safety report (counts only)
      get: () => this.request("GET", "/workspace"),
      safety: ({ days = 30 } = {}) => this.request("GET", `/workspace/safety?days=${encodeURIComponent(days)}`),
    };
    this.webhooks = {
      secret: async () => (await this.request("GET", "/webhooks/secret")).secret,
      rotate: async () => (await this.request("POST", "/webhooks/secret/rotate")).secret,
    };
    this.batches = {                                   // many chat requests at once, answered in the background (up to 100)
      // requests: prompts (strings), message lists, or { custom_id, body: {chat request} } items
      create: (requests, { name = "", model = "" } = {}) => this.request("POST", "/batches", { json: {
        requests: requests.map((r, i) => (r && r.body ? { custom_id: String(r.custom_id || `request-${i + 1}`), body: r.body }
          : { custom_id: `request-${i + 1}`, body: { messages: Array.isArray(r) ? r : [{ role: "user", content: String(r) }], ...(model ? { model } : {}) } })),
        ...(name ? { name } : {}) } }),
      get: (id) => this.request("GET", `/batches/${encodeURIComponent(id)}`),
      list: async () => (await this.request("GET", "/batches")).data || [],
      cancel: (id) => this.request("POST", `/batches/${encodeURIComponent(id)}/cancel`),
      // [{ custom_id, response | error }], one per request
      results: async (id) => (await (await this.request("GET", `/batches/${encodeURIComponent(id)}/results`, { raw: true })).text())
        .split("\n").filter((l) => l.trim()).map((l) => JSON.parse(l)),
      wait: async (id, { every = 2000, timeout = 3600000 } = {}) => {
        const start = Date.now();
        for (;;) {
          const b = await this.batches.get(id);
          if (["completed", "failed", "cancelled", "expired"].includes(b.status) || Date.now() - start > timeout) return b;
          await new Promise((r) => setTimeout(r, every));
        }
      },
    };
    this.audio = {                                     // voice messages in your own app
      // speech to text in any language: a Blob/File, or bytes (Uint8Array / ArrayBuffer) with a filename
      transcribe: async (audio, { filename = "speech.webm", language = "" } = {}) => {
        const form = new FormData();
        const blob = audio instanceof Blob ? audio : new Blob([audio]);
        form.append("file", blob, (audio && audio.name) || filename);
        if (language) form.append("language", language);
        return (await this.request("POST", "/audio/transcriptions", { body: form })).text || "";
      },
      // Gink's natural voice: an ArrayBuffer of WAV audio
      speech: async (text, { voice, speed } = {}) =>
        (await this.request("POST", "/audio/speech", { json: { input: String(text), ...(voice ? { voice } : {}), ...(speed ? { speed } : {}) }, raw: true })).arrayBuffer(),
    };
  }

  // Places by name or address (OpenStreetMap): [{ name, display, lat, lon, type, map_url }]
  async geo(query, { limit = 5 } = {}) {
    return (await this.request("GET", `/geo/search?q=${encodeURIComponent(query)}&limit=${encodeURIComponent(limit)}`)).data || [];
  }

  // The maps in an answer (ask with { gink_maps: true }): [{ title, places: [{ name, query, lat, lon, category, note, map_url }] }]
  maps(text) { return maps(text); }

  // A picture of a place, like the ones on Gink's map cards (Wikipedia's): { image, title, page, credit } -- or null
  async placePhoto(name, lat, lon) {
    try {
      return await this.request("GET", `/places/photo?name=${encodeURIComponent(name)}&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
    } catch (err) {
      if (err && err.status === 404) return null;
      throw err;
    }
  }

  async request(method, path, { json, body, raw } = {}) {
    const headers = { Authorization: `Bearer ${this.apiKey}`, ...placeHeaders(this.location) };
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

  async _chatData(message, { model, system, ...extra } = {}) {
    const messages = Array.isArray(message) ? message
      : [...(system ? [{ role: "system", content: system }] : []), { role: "user", content: String(message) }];
    return this.request("POST", "/chat/completions", { json: { messages, ...(model ? { model } : {}), ...extra } });
  }

  async chat(message, options = {}) {
    const data = await this._chatData(message, options);
    return (((data.choices || [])[0] || {}).message || {}).content || "";
  }

  // An answer from the web, its sources listed (official ones first). { withSources: true } ->
  // { answer, sources: [{ title, url, host, official, icon }] } -- icon: the site's real logo, served by Gink.
  async search(question, { withSources = false } = {}) {
    const data = await this._chatData(question, { model: "gink-search" });
    const text = (((data.choices || [])[0] || {}).message || {}).content || "";
    if (!withSources) return text;
    const found = sources(text, this.baseURL), byUrl = new Map(found.map((s) => [s.url, s]));
    for (const s of data.sources || []) {                     // the server's own list, when it sent one
      const f = s && byUrl.get(s.url);
      if (f) { f.official = !!s.official; f.icon = s.icon || f.icon; }
    }
    return { answer: text, sources: found.sort((a, b) => (b.official ? 1 : 0) - (a.official ? 1 : 0)) };
  }

  sources(text) { return sources(text, this.baseURL); }

  // An answer about a photo -- like the Live camera: Gink works out what it needs (reads text, finds what's wrong,
  // solves sums...) and is careful with anything about health. photo: Uint8Array, base64 or a data URL. (Gink Pro)
  see(photo, { question, model, ...extra } = {}) {
    const content = [{ type: "text", text: String(question || "").trim() || "What's this?" },
                     { type: "image_url", image_url: { url: imageDataURL(photo) } }];
    return this.chat([{ role: "user", content }], { model, ...extra });
  }

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

  // Is Gink working right now? { status: "ok" | "degraded" | "down" | "notice", message, components }
  async status() {
    const base = this.baseURL.replace(/\/v1$/, "");
    return (await this._fetch(base + "/status")).json();
  }

  // Everything Gink's server keeps for this account, as a ZIP (bytes). At most once every 10 minutes.
  async exportAccount() { return new Uint8Array(await (await this.request("GET", "/account/export.zip", { raw: true })).arrayBuffer()); }
}

// Uint8Array, base64 or a data URL -> a data URL Gink can look at (JPEG, PNG, WebP or GIF)
// The sources under a web answer's "Sources" (gink-search), official ones first:
// [{ title, url, host, official, icon }] -- icon: the site's real logo, served by Gink (<server>/icon/<host>).
export function sources(text, baseURL = DEFAULT_BASE_URL) {
  const root = String(baseURL || DEFAULT_BASE_URL).replace(/\/+$/, "").replace(/\/v1$/, "");
  const part = String(text || "").split("**Sources**");
  const out = [];
  for (const line of (part.length > 1 ? part[1] : "").split("\n")) {
    const m = /^\s*[-*]\s*\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)(.*)$/.exec(line);
    if (!m) continue;
    let host = "";
    try { host = new URL(m[2]).hostname.toLowerCase().replace(/^www\./, ""); } catch (e) { host = ""; }
    out.push({ title: m[1].trim() || host, url: m[2], host, official: /\u00b7\s*official\s*$/.test(m[3]),
               icon: host ? `${root}/icon/${host}` : "" });
  }
  return out.sort((a, b) => (b.official ? 1 : 0) - (a.official ? 1 : 0));
}

export function maps(text) {
  const out = [];
  for (const m of String(text || "").matchAll(/```map\s*\n([\s\S]*?)```/g)) {
    let data; try { data = JSON.parse(m[1]); } catch { continue; }
    const places = ((data && (data.places || data.markers)) || []).slice(0, 10)
      .filter((p) => p && (p.name || p.query)).map((p) => {
        const place = {};
        for (const k of ["name", "query", "lat", "lon", "category", "note"]) if (p[k] !== undefined && p[k] !== "") place[k] = p[k];
        if (typeof p.lat === "number" && typeof p.lon === "number")
          place.map_url = `https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=16/${p.lat}/${p.lon}`;
        return place;
      });
    if (places.length) out.push({ title: String(data.title || ""), places });
  }
  return out;
}

export function imageDataURL(photo) {
  if (typeof photo === "string" && photo.startsWith("data:image/")) return photo;
  const bytes = typeof photo === "string" ? base64ToBytes(photo) : new Uint8Array(photo);
  const is = (sig, at = 0) => sig.every((b, i) => bytes[at + i] === b);
  const mime = is([0xff, 0xd8, 0xff]) ? "image/jpeg" : is([0x89, 0x50, 0x4e, 0x47]) ? "image/png"
    : is([0x52, 0x49, 0x46, 0x46]) && is([0x57, 0x45, 0x42, 0x50], 8) ? "image/webp" : is([0x47, 0x49, 0x46, 0x38]) ? "image/gif" : "";
  if (!mime) throw new GinkAPIError("That isn't a JPEG, PNG, WebP or GIF photo.", 400, "invalid_image");
  return `data:${mime};base64,` + (typeof photo === "string" ? photo : bytesToBase64(bytes));
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
  const b = { agent: params.agent || "gink-agent", input: params.input, max_steps: params.max_steps ?? 30, ...extra };
  if (params.previous_interaction_id) b.previous_interaction_id = params.previous_interaction_id;
  else b.environment = params.environment || "remote";
  if (params.tools) b.tools = params.tools;
  if (params.background) b.background = true;
  if (params.webhook_url) b.webhook_url = params.webhook_url;
  if (params.notify_email) b.notify_email = true;
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
  // the whole environment checked (nothing runs): { ok, problems, missing, broken, fix_request }
  check() { return this._c.request("GET", `/environments/${encodeURIComponent(this.id)}/check`); }
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
  create({ input, every = "daily", at = "08:00", timezone, environment = "remote", tools, webhook_url, notify_email } = {}) {
    const body = { input, every, at, environment };
    if (webhook_url) body.webhook_url = webhook_url;
    if (notify_email) body.notify_email = true;
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
