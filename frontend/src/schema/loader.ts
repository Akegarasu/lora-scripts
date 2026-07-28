import { schemasApi, type SchemaSource } from "../api/schemas"
import { executeSchemaSources } from "./adapter"

const CACHE_KEY = "schemas"

function readCache(): SchemaSource[] {
  try {
    const value = JSON.parse(localStorage.getItem(CACHE_KEY) || "[]")
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export async function loadTrainingSchema(name: string) {
  let sources = readCache()
  try {
    const { schemas: hashes } = await schemasApi.hashes()
    const current = new Map(sources.map((item) => [item.name, item.hash]))
    const stale = hashes.length !== sources.length || hashes.some((item) => current.get(item.name) !== item.hash)
    if (stale) {
      sources = (await schemasApi.all()).schemas
      localStorage.setItem(CACHE_KEY, JSON.stringify(sources))
    }
  } catch (error) {
    if (!sources.length) throw error
  }
  return executeSchemaSources(sources, name)
}
