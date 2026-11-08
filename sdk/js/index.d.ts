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
}

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
  refresh(): Promise<Environment>;
  delete(): Promise<{ id: string; deleted: true }>;
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
  chat(message: string | Array<{ role: string; content: string }>, options?: { model?: string; system?: string }): Promise<string>;
  search(question: string): Promise<string>;
  image(prompt?: string, options?: { idea?: string; subject?: string; style?: string;
    aspect_ratio?: "1:1" | "16:9" | "9:16" | "4:3" | "3:4"; photo?: Uint8Array | string }): Promise<Uint8Array>;
  imageIdeas(): Promise<{ styles: Array<{ id: string; description: string }>;
    ideas: Array<{ id: string; title: string; prompt: string; example_subject: string; style: string; aspect_ratio: string }> }>;
  models(): Promise<string[]>;
}

export default Gink;
