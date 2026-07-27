import { apiRequest } from "./client"

export const AVAILABLE_SCRIPTS = [
  "networks/extract_lora_from_models.py",
  "networks/extract_lora_from_dylora.py",
  "networks/merge_lora.py",
  "tools/merge_models.py",
] as const

export type ToolScript = typeof AVAILABLE_SCRIPTS[number]

export const toolsApi = {
  run: (scriptName: ToolScript, args: Record<string, string | number | boolean>) => apiRequest("/api/run_script", {
    method: "POST",
    body: JSON.stringify({ script_name: scriptName, ...args }),
  }),
}
