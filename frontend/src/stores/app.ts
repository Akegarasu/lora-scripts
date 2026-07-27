import { defineStore } from "pinia"
import { ref } from "vue"
import { systemApi } from "../api/system"

export const useAppStore = defineStore("app", () => {
  const version = ref("")

  async function loadVersion() {
    try {
      version.value = (await systemApi.getVersion()).version
    } catch {
      version.value = ""
    }
  }

  return { version, loadVersion }
})
