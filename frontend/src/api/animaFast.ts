import { apiData } from "./client"

export interface AnimaFastStatus {
  state: string
  feature_enabled: boolean
  message?: string
  facts?: { task_id?: string; audit?: { ok?: boolean; errors?: string[] } }
  runtime?: Record<string, unknown>
}

export interface InstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  log_stream_url?: string
  progress_stream?: string
  progress_stream_url?: string
  status?: AnimaFastStatus
}

export const animaFastApi = {
  status: () => apiData<AnimaFastStatus>("/api/plugins/anima-lora/status"),
  install: () => apiData<InstallResult>("/api/plugins/anima-lora/install", { method: "POST", body: JSON.stringify({ dry_run: false }) }),
  repair: () => apiData<InstallResult>("/api/plugins/anima-lora/repair", { method: "POST", body: JSON.stringify({ dry_run: false }) }),
}
