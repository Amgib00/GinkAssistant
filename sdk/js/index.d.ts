export declare const DEFAULT_BASE_URL: string;

export declare class GinkAPIError extends Error {
  status: number;
  code: string;
}

export interface Step { tool: string; path?: string; query?: string; changed?: boolean; result?: string }

export interface Interaction {
  id: string;
  object: "interaction";
  agent: string;
  status: "running" | "completed" | "incomplete" | "failed" | "cancelled";
  environment: string;
  output_text: string;
  steps: Step[];
  files_changed: string[];
  previous_interaction_id: string | null;
  created: number;
  finished: number | null;
  usage: { steps: number };
  error?: { message: string };
}

export interface InteractionParams {
  input: string;
  agent?: "gink-agent";
  environment?: string;            // "remote" for a new one, or an environment id
  previous_interaction_id?: string;
  background?: boolean;
  max_steps?: number;              // 1-30, default 15
  tools?: Array<"files" | "web_search">;
  notify_email?: boolean;          // email the account the result when it ends
  webhook_url?: string;            // https: Gink POSTs {"type": "interaction.<status>", "data": Interaction} when it ends
}

/** Uint8Array, base64 or a data URL -> a data URL Gink can look at (JPEG, PNG, WebP or GIF). */
export declare function imageDataURL(photo: Uint8Array | ArrayBuffer | string): string;
/** A source of a web answer: official = a government, an international body or the organisation's own site;
 *  icon = the site's real logo, served by Gink (<server>/icon/<host>). */
export interface Source { title: string; url: string; host: string; official: boolean; icon: string }
export declare function sources(text: string, baseURL?: string): Source[];
export declare function verifyWebhook(body: string, signature: string, secret: string,
  options?: { tolerance?: number }): Promise<{ type: string; data: Interaction }>;

export type InteractionEvent =
  | { type: "step"; data: Step }
  | { type: "status"; data: { id: string; status: Interaction["status"] } }
  | { type: "done"; data: Interaction };

export declare class Environment {
  id: string;
  name: string;
  files: Array<{ path: string; size: number }>;
  preview_url: string;
  upload(path: string, content: string | Uint8Array | Blob): Promise<Environment>;
  download(path: string): Promise<Uint8Array>;
  text(path: string): Promise<string>;
  check(): Promise<{ ok: boolean; files: number; problems: string[]; missing: string[]; broken: string[]; fix_request: string }>;
  refresh(): Promise<Environment>;
  delete(): Promise<{ id: string; deleted: true }>;
}

export interface SafetyCounts { patient_details_removed: number; patient_details_stopped: number; photo_checked: number }
export interface SafetyReport {
  object: "safety_report"; days: number; since: string; totals: SafetyCounts;
  by_day: Array<SafetyCounts & { day: string }>; by_person: Array<SafetyCounts & { account: string; name: string }>;
  by_feature: Record<string, number>; workspace?: { id: string; name: string; healthcare: boolean };
}

export interface Schedule {
  id: string; object: "schedule"; input: string; every: "hourly" | "daily" | "weekly"; at: string; timezone: string;
  environment: string; tools: Array<"files" | "web_search">; enabled: boolean; next_run: number; last_run: number | null;
  last_interaction_id: string | null; created: number; notify_email: boolean; webhook_url?: string;
}

export declare class Gink {
  constructor(options?: { apiKey?: string; baseURL?: string; fetch?: typeof fetch });
  interactions: {
    create(params: InteractionParams): Promise<Interaction>;
    stream(params: InteractionParams): AsyncIterable<InteractionEvent>;
    get(id: string): Promise<Interaction>;
    cancel(id: string): Promise<Interaction>;
    wait(id: string, options?: { every?: number; timeout?: number }): Promise<Interaction>;
  };
  environments: {
    create(options?: { name?: string }): Promise<Environment>;
    list(): Promise<Environment[]>;
    get(id: string): Promise<Environment>;
  };
  schedules: {
    create(params: { input: string; every?: Schedule["every"]; at?: string; timezone?: string; environment?: string;
      tools?: Array<"files" | "web_search">; webhook_url?: string; notify_email?: boolean }): Promise<Schedule>;
    list(): Promise<Schedule[]>;
    run(id: string): Promise<{ schedule: Schedule; interaction_id: string | null }>;
    pause(id: string): Promise<Schedule>;
    resume(id: string): Promise<Schedule>;
    delete(id: string): Promise<{ id: string; deleted: true }>;
  };
  webhooks: { secret(): Promise<string>; rotate(): Promise<string> };
  workspace: {
    get(): Promise<{ workspace: { id: string; name: string; healthcare: boolean; patient_details: "remove" | "stop" } | null;
      role?: "admin" | "member"; status?: "active" | "invited" }>;
    /** Admins: healthcare mode's safety report -- counts only, never words. */
    safety(options?: { days?: number }): Promise<SafetyReport>;
  };
  memories: {
    list(): Promise<Array<{ id: string; text: string; created: number }>>;
    add(text: string): Promise<{ id: string; text: string; replaced: string | null }>;
    forget(id: string): Promise<{ id: string; deleted: true }>;
    suggest(text: string): Promise<string | null>;
  };
  chat(message: string | Array<{ role: string; content: string | Array<Record<string, unknown>> }>,
       options?: { model?: string; system?: string }): Promise<string>;
  /** An answer from the web, its sources listed (official ones first); { withSources: true } adds them as data. */
  search(question: string): Promise<string>;
  search(question: string, options: { withSources: true }): Promise<{ answer: string; sources: Source[] }>;
  /** The sources under an answer's "Sources", each with its site's real logo. */
  sources(text: string): Source[];
  /** An answer about a photo (like the Live camera); careful with anything about health. Gink Pro. */
  see(photo: Uint8Array | ArrayBuffer | string, options?: { question?: string; model?: string }): Promise<string>;
  image(prompt?: string, options?: { idea?: string; subject?: string; style?: string;
    aspect_ratio?: "1:1" | "16:9" | "9:16" | "4:3" | "3:4"; photo?: Uint8Array | string }): Promise<Uint8Array>;
  imageIdeas(): Promise<{ styles: Array<{ id: string; description: string }>;
    ideas: Array<{ id: string; title: string; prompt: string; example_subject: string; style: string; aspect_ratio: string }>;
    looks: Array<{ id: string; title: string; prompt: string; example_subject: string; style: string; aspect_ratio: string }> }>;
  models(): Promise<string[]>;
  exportAccount(): Promise<Uint8Array>;
  status(): Promise<{ status: "ok" | "degraded" | "down" | "notice"; message: string;
    components: Record<"chat" | "images" | "search" | "email" | "storage", "ok" | "degraded" | "down">; checked: number }>;
}

export default Gink;
