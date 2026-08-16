import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type { ParamDefinition, ParamGroup, TrainerSummary } from '@/api/types'

let paramsRequestId = 0
let allParamsRequestId = 0

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    trainers: [] as TrainerSummary[],
    groups: [] as ParamGroup[],
    allGroups: [] as ParamGroup[],
    groupsTrainerId: '',
    allGroupsTrainerId: '',
    allGroupsManifestHash: '',
    manifestHash: '',
    selectedTrainerId: '',
    view: 'recommended',
    loading: false,
    error: '',
  }),
  getters: {
    selectedTrainer(state) {
      return state.trainers.find((trainer) => trainer.id === state.selectedTrainerId)
    },
    visibleParams(state) {
      return state.groups.flatMap((group) => group.params)
    },
    modelGroup(state) {
      return state.groups.find((group) => group.id === 'model')
    },
    nonModelGroups(state) {
      return state.groups.filter((group) => group.id !== 'model' && group.params.length > 0)
    },
    allParams(state): ParamDefinition[] {
      return state.allGroups.flatMap((group) => group.params)
    },
    groupTitles(state): Record<string, string> {
      const map: Record<string, string> = {}
      for (const group of state.allGroups) map[group.id] = group.title
      return map
    },
  },
  actions: {
    async loadTrainers() {
      this.loading = true
      this.error = ''
      try {
        const data = await apiClient.listTrainers()
        this.trainers = data.trainers
        this.manifestHash = data.manifestHash
        if (!this.selectedTrainerId && data.trainers.length > 0) {
          this.selectedTrainerId = data.trainers.find((item) => item.id === 'flux.lora')?.id || data.trainers[0].id
        }
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async loadParams() {
      if (!this.selectedTrainerId) {
        this.groups = []
        this.groupsTrainerId = ''
        return
      }
      const requestId = ++paramsRequestId
      const trainerId = this.selectedTrainerId
      const view = this.view
      if (this.groupsTrainerId !== trainerId) {
        this.groups = []
        this.groupsTrainerId = ''
      }
      this.loading = true
      this.error = ''
      try {
        const data = await apiClient.getTrainerParams(trainerId, view)
        if (requestId !== paramsRequestId || trainerId !== this.selectedTrainerId || view !== this.view) return
        this.groups = data.groups
        this.groupsTrainerId = trainerId
        this.manifestHash = data.manifestHash
      } catch (error) {
        if (requestId !== paramsRequestId) return
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        if (requestId === paramsRequestId) this.loading = false
      }
    },
    async loadAllParams() {
      if (!this.selectedTrainerId) {
        this.allGroups = []
        this.allGroupsTrainerId = ''
        this.allGroupsManifestHash = ''
        return
      }
      const requestId = ++allParamsRequestId
      const trainerId = this.selectedTrainerId
      if (this.allGroupsTrainerId !== trainerId) {
        this.allGroups = []
        this.allGroupsTrainerId = ''
        this.allGroupsManifestHash = ''
      }
      try {
        const data = await apiClient.getTrainerParams(trainerId, 'all')
        if (requestId !== allParamsRequestId || trainerId !== this.selectedTrainerId) return
        this.allGroups = data.groups
        this.allGroupsTrainerId = trainerId
        this.allGroupsManifestHash = data.manifestHash
        this.manifestHash = data.manifestHash
      } catch (error) {
        if (requestId !== allParamsRequestId) return
        this.error = error instanceof Error ? error.message : String(error)
      }
    },
  },
})
