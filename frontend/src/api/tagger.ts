import { apiData, apiRequest } from "./client"

export type TaggerPhase = "idle" | "downloading" | "tagging" | "done" | "error" | "pending" | "cancelling"
export interface TaggerStep { current: number; total: number; filename: string; bytes_current: number; bytes_total: number; percent: number }
export interface TaggerStatus { phase: TaggerPhase; message: string; model: string; download: TaggerStep; tagging: TaggerStep; error?: string | null; updated_at: number }
export interface TaggerRequest {
  path: string; interrogator_model: string; threshold: number; character_threshold: number
  add_rating_tag: boolean; add_model_tag: boolean; additional_tags: string; exclude_tags: string
  escape_tag: boolean; batch_input_recursive: boolean; batch_output_action_on_conflict: string
  replace_underscore: boolean; download_endpoint: string; replace_underscore_excludes: string
}

export const taggerApi = {
  status: () => apiData<TaggerStatus>("/api/tagger/status"),
  start: (body: TaggerRequest) => apiRequest("/api/interrogate", { method: "POST", body: JSON.stringify(body) }),
  prefetch: (interrogator_model: string, download_endpoint: string) => apiRequest("/api/tagger/prefetch", { method: "POST", body: JSON.stringify({ interrogator_model, download_endpoint }) }),
  cancel: () => apiRequest("/api/tagger/cancel", { method: "POST" }),
  reset: () => apiRequest("/api/tagger/reset", { method: "POST" }),
}
