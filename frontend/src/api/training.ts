import { apiData } from "./client"
import type { FormModel } from "../schema/adapter"

export interface TrainingPreset {
  metadata: {
    name: string
    version?: string
    author?: string
    train_type?: string
    description?: string
  }
  data: FormModel
}

export interface ImportValidation {
  result: "ok" | "redirect" | "reject"
  config?: FormModel
  forced_train_type?: string
  target_path?: string
  message?: string
  notice?: string
  errors?: string[]
}

export interface NormalizedExport {
  config: FormModel
  warnings: string[]
}

export interface TrainingStart {
  task_id: string
  train_log_url?: string
  train_log_path?: string
  train_log_query?: string
  metadata?: Record<string, unknown>
}

export interface PreflightResult {
  ok: boolean
  errors?: string[]
  warnings?: string[]
  [key: string]: unknown
}

function post<T>(path: string, body: unknown) {
  return apiData<T>(path, { method: "POST", body: JSON.stringify(body) })
}

export const trainingApi = {
  presets: async () => (await apiData<{ presets: TrainingPreset[] }>("/api/presets")).presets,
  validateImport: (pageTrainType: string, config: FormModel) => post<ImportValidation>("/api/config/validate-import", { page_train_type: pageTrainType, config }),
  normalizeExport: (pageTrainType: string, config: FormModel) => post<NormalizedExport>("/api/config/normalize-for-export", { page_train_type: pageTrainType, config }),
  run: (config: FormModel) => post<TrainingStart>("/api/run", config),
  animaFastPreflight: (config: FormModel) => post<PreflightResult>("/api/anima-fast/preflight", config),
}
