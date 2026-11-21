export declare const DEFAULT_BASE_URL: string;
export interface Batch { id: string; object: "batch"; name: string | null; status: string; created_at: number;
  completed_at: number | null; request_counts: { total: number; completed: number; failed: number } }
/** category: food, cafe, bar, shop, museum, sight, park, beach, hotel, transport, health, school, worship or other. */
export interface MapPlace { name?: string; query?: string; lat?: number; lon?: number; category?: string; note?: string; map_url?: string }
/** A picture of a place (Wikipedia's), as on Gink's map cards. */
export interface PlacePhoto { image: string; title: string; page: string; credit: string; object?: "place_photo" }
/** The maps in an answer (```map blocks; ask with { gink_maps: true }). */
export declare function maps(text: string): Array<{ title: string; places: MapPlace[] }>;
/** A finished thing in an answer (a titled block; ask with { gink_artifacts: true }). */
export interface Artifact { title: string; language: string; kind: "page" | "image" | "diagram" | "document" | "code";
  content: string; filename: string; version: number }
/** The finished things in an answer: each fenced block with a title (a later one with the same title is its next version). */
export declare function artifacts(text: string): Artifact[];
/** A schedule an answer offers (a ```schedule block; ask with { gink_tasks: true }), ready for gink.tasks.create(). */
export interface ScheduleOffer { title?: string; task: string; every?: Task["every"]; at?: string; day?: string | number; date?: string }
export declare function schedulesIn(text: string): ScheduleOffer[];
/** The clock's offset from UTC, like "+01:00". */
export declare function utcOffset(): string;

export declare class GinkAPIError extends Error {
  status: number;
  code: string;
}

export interface Step { tool: string; path?: string; query?: string; changed?: boolean; result?: string;
  plan?: Array<{ title: string; status: "todo" | "doing" | "done" }> }

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
  /** The agent's plan (update_plan), as it last wrote it. */
  plan: Array<{ title: string; status: "todo" | "doing" | "done" }>;
  error?: { message: string };
}

export interface InteractionParams {
  input: string;
  agent?: "gink-agent";
  environment?: string;            // "remote" for a new one, or an environment id
  previous_interaction_id?: string;
  background?: boolean;
  max_steps?: number;              // 1-60, default 30
  tools?: Array<"files" | "web_search">;
  notify_email?: boolean;          // email the account the result when it ends
  webhook_url?: string;            // https: Gink POSTs {"type": "interaction.<status>", "data": Interaction} when it ends
}

/** Uint8Array, base64 or a data URL -> a data URL Gink can look at (JPEG, PNG, WebP or GIF). */
export declare function imageDataURL(photo: Uint8Array | ArrayBuffer | string): string;
/** A video as Gink's apps send it (0.1.162): a sentence saying what the pictures are, then up to five frames in order. */
export declare function videoParts(frames: Array<Uint8Array | ArrayBuffer | string>,
                                   options?: { question?: string; name?: string; duration?: number; times?: number[] }): unknown[];
/** In a browser: frames from a video File, Blob or URL (<video> + canvas), as data URLs, with their moments. */
export declare function videoFrames(video: Blob | string, options?: { count?: number }):
  Promise<{ frames: string[]; times: number[]; duration: number }>;
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

/** A scheduled task: Gink does it by itself at its time; the result lands in its own chat in your Gink apps. */
export interface Task {
  id: string; object: "task"; title: string; task: string;
  every: "once" | "hourly" | "daily" | "weekdays" | "weekly" | "monthly"; at: string;
  /** weekly: 0 = Monday ... 6 = Sunday; monthly: 1-31 */
  day?: number; date?: string; timezone: string; when: string; chat_id: string; enabled: boolean; notify_email: boolean;
  next_run: number | null; last_run: number | null; last_status: "ok" | "skipped" | "failed" | "retrying" | null;
  last_note: string; runs: number; created: number; source?: string; existing?: boolean;
  results?: Array<{ text: string; created: number }>;
}
export interface Schedule {
  id: string; object: "schedule"; input: string; every: "hourly" | "daily" | "weekdays" | "weekly"; at: string; timezone: string;
  environment: string; tools: Array<"files" | "web_search">; enabled: boolean; next_run: number; last_run: number | null;
  last_interaction_id: string | null; created: number; notify_email: boolean; webhook_url?: string;
}

export declare class Gink {
  /** location: false -- no location metadata (city/region) is sent, only the clock's UTC offset (or GINK_LOCATION=off). */
  constructor(options?: { apiKey?: string; baseURL?: string; fetch?: typeof fetch; location?: boolean });
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
  /** Scheduled tasks: Free 3, Pro 25 (and hourly); each run counts as one message. */
  tasks: {
    create(params: { task: string; every?: Task["every"]; at?: string; title?: string; day?: string | number; date?: string;
      timezone?: string; notify_email?: boolean }): Promise<Task>;
    list(): Promise<Task[]>;
    get(id: string, options?: { results?: number }): Promise<Task>;
    update(id: string, fields: Partial<Pick<Task, "title" | "task" | "every" | "at" | "day" | "date" | "timezone" | "notify_email" | "enabled">>): Promise<Task>;
    pause(id: string): Promise<Task>;
    resume(id: string): Promise<Task>;
    /** Run it now; wait (default): its result in the answer. */
    run(id: string, options?: { wait?: boolean }): Promise<{ task: Task; status: string; text?: string; note?: string }>;
    delete(id: string): Promise<{ id: string; deleted: true }>;
  };
  webhooks: { secret(): Promise<string>; rotate(): Promise<string> };
  workspace: {
    get(): Promise<{ workspace: { id: string; name: string; healthcare: boolean; patient_details: "remove" | "stop" } | null;
      role?: "admin" | "member"; status?: "active" | "invited" }>;
    /** Admins: healthcare mode's safety report -- counts only, never words. */
    safety(options?: { days?: number }): Promise<SafetyReport>;
  };
  /** Many chat requests at once, answered in the background (up to 100). */
  batches: {
    create(requests: Array<string | Array<{ role: string; content: string }> | { custom_id?: string; body: object }>,
           options?: { name?: string; model?: string }): Promise<Batch>;
    get(id: string): Promise<Batch>;
    list(): Promise<Batch[]>;
    cancel(id: string): Promise<Batch>;
    results(id: string): Promise<Array<{ custom_id: string; response?: any; error?: { message: string } }>>;
    wait(id: string, options?: { every?: number; timeout?: number }): Promise<Batch>;
  };
  /** Voice messages in your own app. */
  audio: {
    /** Speech to text in any language (WAV, WebM, OGG, M4A/MP4, MP3, FLAC). */
    transcribe(audio: Blob | ArrayBuffer | Uint8Array, options?: { filename?: string; language?: string }): Promise<string>;
    /** Gink's natural voice: WAV audio. */
    speech(text: string, options?: { voice?: string; speed?: "slow" | "fast" }): Promise<ArrayBuffer>;
  };
  /** Places by name or address (OpenStreetMap). */
  geo(query: string, options?: { limit?: number }): Promise<Array<{ name: string; display: string; lat: number; lon: number;
    type: string; map_url: string }>>;
  /** The maps in an answer (ask with { gink_maps: true }). */
  maps(text: string): Array<{ title: string; places: MapPlace[] }>;
  /** The finished things in an answer (ask with { gink_artifacts: true }). */
  artifacts(text: string): Artifact[];
  /** The schedules an answer offers (ask with { gink_tasks: true }). */
  schedulesIn(text: string): ScheduleOffer[];
  /** A picture of a place, like the ones on Gink's map cards -- null when there's none. */
  placePhoto(name: string, lat: number, lon: number): Promise<PlacePhoto | null>;
  memories: {
    list(): Promise<Array<{ id: string; text: string; created: number }>>;
    add(text: string): Promise<{ id: string; text: string; replaced: string | null }>;
    forget(id: string): Promise<{ id: string; deleted: true }>;
    suggest(text: string, options?: { sensitive?: boolean }): Promise<string | null>;
    /** "Generate memory from chats": the lasting facts in a conversation (at most 5), saved unless save: false.
     *  sensitive: also health, religion and other sensitive topics (never for teens' accounts). */
    generate(messages: Array<{ role: string; content: string }>, options?: { save?: boolean; sensitive?: boolean }):
      Promise<Array<{ id?: string; text: string; replaced?: string | null }>>;
    /** What to ask your other AI assistant so it lists what it remembers about you. */
    importPrompt(): Promise<string>;
    /** "Import memory from other AI providers": its answer (one fact per line), added to memory. */
    import(text: string, options?: { sensitive?: boolean }): Promise<{ data: Array<{ id: string; text: string; replaced: string | null }>;
      skipped: number; skipped_sensitive: number; memory_full: boolean }>;
  };
  /** gink_maps: true -- answers about places end with a ```map block (read it with maps()); gink_artifacts: finished
   *  things in titled blocks (artifacts()); gink_tasks: "every morning..." gets a ```schedule block (schedulesIn());
   *  gink_web: "auto" reads linked pages and searches when needed; gink_code: GitHub repositories are read. */
  chat(message: string | Array<{ role: string; content: string | Array<Record<string, unknown>> }>,
       options?: { model?: string; system?: string; gink_maps?: boolean; gink_artifacts?: boolean; gink_tasks?: boolean;
                   gink_web?: boolean | "auto"; gink_code?: boolean }): Promise<string>;
  /** An answer from the web, its sources listed (official ones first); { withSources: true } adds them as data. */
  search(question: string): Promise<string>;
  search(question: string, options: { withSources: true }): Promise<{ answer: string; sources: Source[] }>;
  /** The sources under an answer's "Sources", each with its site's real logo. */
  sources(text: string): Source[];
  /** An answer about a photo (like the Live camera); careful with anything about health. Gink Pro. */
  see(photo: Uint8Array | ArrayBuffer | string, options?: { question?: string; model?: string }): Promise<string>;
  /** An answer about a video from its frames (in a browser, videoFrames() takes them). Gink Pro. */
  watch(frames: Array<Uint8Array | ArrayBuffer | string>,
        options?: { question?: string; model?: string; name?: string; duration?: number; times?: number[] }): Promise<string>;
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
