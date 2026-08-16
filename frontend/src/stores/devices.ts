import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type { GpuInfo } from '@/api/types'

export const useDevicesStore = defineStore('devices', {
  state: () => ({
    gpus: [] as GpuInfo[],
    loading: false,
    error: '',
  }),
  actions: {
    async loadGpus() {
      this.loading = true
      this.error = ''
      try {
        const data = await apiClient.listGpus()
        this.gpus = data.gpus
        this.error = data.error || ''
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
  },
})
