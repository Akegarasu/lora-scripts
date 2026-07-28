import { apiData, apiRequest } from "./client"

export interface SchemaSource {
  name: string
  schema: string
  hash: string
}

export interface SchemaHash {
  name: string
  hash: string
}

export interface GraphicCard {
  label?: string
  value?: string | number
  [key: string]: unknown
}

export interface PickerFile {
  path: string
  name: string
  size?: string
  size_bytes?: number
  mtime?: number
}

export const schemasApi = {
  hashes: () => apiData<{ schemas: SchemaHash[] }>("/api/schemas/hashes"),
  all: () => apiData<{ schemas: SchemaSource[] }>("/api/schemas/all"),
  async graphicCards() {
    const response = await apiRequest<{ cards: Array<string | number | GraphicCard> }>("/api/graphic_cards", { allowPending: true })
    return response.status === "success" ? response.data?.cards ?? [] : []
  },
  pickFile: (pickerType: string) => apiData<{ path: string }>(`/api/pick_file?picker_type=${encodeURIComponent(pickerType)}`),
  files: (pickType: string) => apiData<{ files: PickerFile[] }>(`/api/get_files?pick_type=${encodeURIComponent(pickType)}`),
}
