import { apiData } from "./client"

export interface DatasetItem { name: string; relative_path: string; category: string; caption: string; caption_exists: boolean; tags: string[]; image_url: string }
export interface DatasetScan { root: string; total: number; items: DatasetItem[]; tags: Array<{ tag: string; count: number }>; categories: Array<{ name: string; value: string; count: number }> }
export interface ChangedItem { image: string; caption: string; caption_exists: boolean; tags: string[] }
export interface TagReplacement { from: string; to: string }
export interface DatasetMutation { changed: number; items: ChangedItem[] }
export interface BatchEditRequest {
  root: string
  images: string[]
  append?: string[]
  remove?: string[]
  replace?: TagReplacement[]
  sort?: boolean
  clean?: boolean
  underscore_to_space?: boolean
  strip_escape_chars?: boolean
}
export interface HistoryItem { image: string; before: string; after: string; before_exists: boolean; after_exists: boolean }
export interface HistoryChange { label: string; count: number; items: HistoryItem[] }
export interface DatasetHistory { can_undo: boolean; can_redo: boolean; changes: HistoryChange[] }

const post = <T>(path: string, body: unknown) => apiData<T>(path, { method: "POST", body: JSON.stringify(body) })
export const datasetApi = {
  scan: (path: string) => post<DatasetScan>("/api/dataset-editor/scan", { path }),
  save: (root: string, image: string, caption: string) => post<ChangedItem>("/api/dataset-editor/caption", { root, image, caption }),
  batch: (body: BatchEditRequest) => post<DatasetMutation>("/api/dataset-editor/batch", body),
  undo: (root: string) => post<DatasetMutation>("/api/dataset-editor/undo", { root }),
  redo: (root: string) => post<DatasetMutation>("/api/dataset-editor/redo", { root }),
  history: (root: string) => post<DatasetHistory>("/api/dataset-editor/history", { root }),
}
