import { computed, ref } from "vue"
import { defineStore } from "pinia"
import { taggerApi, type TaggerRequest, type TaggerStatus } from "../api/tagger"

const idle: TaggerStatus = { phase: "idle", message: "配置参数后点击启动", model: "", download: { current: 0, total: 0, filename: "", bytes_current: 0, bytes_total: 0, percent: 0 }, tagging: { current: 0, total: 0, filename: "", bytes_current: 0, bytes_total: 0, percent: 0 }, updated_at: 0 }
export const useTaggerStore = defineStore("tagger", () => {
  const status = ref<TaggerStatus>(idle)
  const error = ref("")
  const submitting = ref(false)
  const busy = computed(() => ["downloading", "tagging", "pending", "cancelling"].includes(status.value.phase))
  async function refresh() { try { status.value = await taggerApi.status(); error.value = "" } catch (e) { error.value = e instanceof Error ? e.message : "状态读取失败" } }
  async function action(run: () => Promise<unknown>) { submitting.value = true; try { await run(); await refresh() } finally { submitting.value = false } }
  return { status, error, submitting, busy, refresh, start: (body: TaggerRequest) => action(() => taggerApi.start(body)), prefetch: (model: string, endpoint: string) => action(() => taggerApi.prefetch(model, endpoint)), cancel: () => action(taggerApi.cancel), reset: () => action(taggerApi.reset) }
})
