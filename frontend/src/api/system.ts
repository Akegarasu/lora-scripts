import { apiData } from "./client"

export interface VersionData {
  version: string
}

export const systemApi = {
  getVersion: () => apiData<VersionData>("/api/version"),
}
