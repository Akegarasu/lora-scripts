import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type {
  TagEditorChangeResult,
  TagEditorChangeSetSummary,
  TagEditorDatasetItem,
  TagEditorDatasetItemDetail,
  TagEditorDatasetSummary,
  TagEditorInspectRequest,
  TagEditorItemState,
  TagEditorOperation,
  TagEditorPreviewResponse,
  TagEditorScope,
  TagEditorSort,
  TagEditorTagCount,
} from '@/api/types'

export type TagEditorSelectionMode = 'explicit' | 'filter'

let inspectRequestVersion = 0
let itemsRequestVersion = 0
let itemsLoadingVersion = 0
let detailRequestVersion = 0
let detailLoadingVersion = 0
let suggestionsRequestVersion = 0
let suggestionsLoadingVersion = 0
let previewRequestVersion = 0
let previewLoadingVersion = 0
let historyRequestVersion = 0
let historyLoadingVersion = 0
let changeRequestVersion = 0
let changeLoadingVersion = 0
let resultsRequestVersion = 0
let resultsLoadingVersion = 0
let changePollVersion = 0
let changePollTimer: number | undefined

const CHANGE_POLL_INTERVAL = 800

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error)
}

function uniqueIds(ids: string[]) {
  return [...new Set(ids.filter(Boolean))]
}

function cloneScope(scope: TagEditorScope): TagEditorScope {
  return scope.mode === 'include'
    ? { mode: 'include', includeIds: [...scope.includeIds] }
    : {
        mode: 'filter',
        query: scope.query,
        state: scope.state,
        exclusions: [...scope.exclusions],
      }
}

function cloneOperation(operation: TagEditorOperation): TagEditorOperation {
  if (operation.type === 'add' || operation.type === 'remove') {
    return { ...operation, values: [...operation.values] }
  }
  return { ...operation }
}

function normalizePageSize(size: number) {
  if (!Number.isFinite(size)) return 100
  return Math.max(1, Math.min(500, Math.trunc(size)))
}

function isFinishedChange(change: TagEditorChangeSetSummary) {
  return new Set([
    'completed',
    'partial',
    'failed',
    'rolled_back',
    'rollback_partial',
    'interrupted',
  ]).has(change.state)
}

export const useTagEditorStore = defineStore('tagEditor', {
  state: () => ({
    dataset: null as TagEditorDatasetSummary | null,
    lastInspectRequest: null as TagEditorInspectRequest | null,
    items: [] as TagEditorDatasetItem[],
    itemsTotal: 0,
    itemsOffset: 0,
    itemsLimit: 100,
    query: '',
    itemState: 'all' as TagEditorItemState,
    sort: 'path_asc' as TagEditorSort,
    commonTags: [] as TagEditorTagCount[],
    inspecting: false,
    itemsLoading: false,
    inspectError: '',
    itemsError: '',

    activeItemId: '',
    activeItem: null as TagEditorDatasetItemDetail | null,
    detailLoading: false,
    detailError: '',

    selectionMode: 'explicit' as TagEditorSelectionMode,
    selectedIds: [] as string[],
    excludedIds: [] as string[],
    selectionQuery: '',
    selectionState: 'all' as TagEditorItemState,
    selectionTotal: 0,

    tagSuggestions: [] as TagEditorTagCount[],
    suggestionsLoading: false,
    suggestionsError: '',

    pendingOperations: [] as TagEditorOperation[],
    preview: null as TagEditorPreviewResponse | null,
    previewScope: null as TagEditorScope | null,
    previewing: false,
    previewError: '',
    applying: false,
    applyError: '',

    changeHistory: [] as TagEditorChangeSetSummary[],
    historyLoading: false,
    historyError: '',
    currentChangeId: '',
    currentChange: null as TagEditorChangeSetSummary | null,
    changeLoading: false,
    changePolling: false,
    changeError: '',
    changeResults: [] as TagEditorChangeResult[],
    changeResultsTotal: 0,
    changeResultsOffset: 0,
    changeResultsLimit: 100,
    resultsLoading: false,
    resultsError: '',
    rollingBackChangeId: '',
    rollbackError: '',
  }),

  getters: {
    currentPage(state): number {
      return Math.floor(state.itemsOffset / state.itemsLimit) + 1
    },
    pageCount(state): number {
      return Math.max(1, Math.ceil(state.itemsTotal / state.itemsLimit))
    },
    selectionCount(state): number {
      if (state.selectionMode === 'filter') {
        return Math.max(0, state.selectionTotal - state.excludedIds.length)
      }
      return state.selectedIds.length
    },
    selectionScope(state): TagEditorScope | null {
      if (state.selectionMode === 'filter') {
        if (state.selectionTotal <= state.excludedIds.length) return null
        return {
          mode: 'filter',
          query: state.selectionQuery,
          state: state.selectionState,
          exclusions: [...state.excludedIds],
        }
      }
      if (!state.selectedIds.length) return null
      return { mode: 'include', includeIds: [...state.selectedIds] }
    },
    isItemSelected(state): (itemId: string) => boolean {
      if (state.selectionMode === 'filter') {
        const excluded = new Set(state.excludedIds)
        return (itemId) => !excluded.has(itemId)
      }
      const selected = new Set(state.selectedIds)
      return (itemId) => selected.has(itemId)
    },
    hasPendingOperations(state): boolean {
      return state.pendingOperations.length > 0
    },
    canApplyPreview(state): boolean {
      return state.preview?.state === 'previewed' && state.preview.changed > 0 && !state.applying
    },
  },

  actions: {
    invalidatePreview() {
      previewRequestVersion += 1
      this.preview = null
      this.previewScope = null
      this.previewing = false
      this.previewError = ''
      this.applyError = ''
    },

    clearSelection() {
      this.selectionMode = 'explicit'
      this.selectedIds = []
      this.excludedIds = []
      this.selectionQuery = ''
      this.selectionState = 'all'
      this.selectionTotal = 0
      this.invalidatePreview()
    },

    selectExplicit(itemIds: string[]) {
      this.selectionMode = 'explicit'
      this.selectedIds = uniqueIds(itemIds)
      this.excludedIds = []
      this.selectionQuery = ''
      this.selectionState = 'all'
      this.selectionTotal = this.selectedIds.length
      this.invalidatePreview()
    },

    selectAllFiltered() {
      this.selectionMode = 'filter'
      this.selectedIds = []
      this.excludedIds = []
      this.selectionQuery = this.query
      this.selectionState = this.itemState
      this.selectionTotal = this.itemsTotal
      this.invalidatePreview()
    },

    toggleItemSelection(itemId: string, selected?: boolean) {
      if (!itemId) return
      const currentlySelected = this.isItemSelected(itemId)
      const nextSelected = selected ?? !currentlySelected
      if (nextSelected === currentlySelected) return

      if (this.selectionMode === 'filter') {
        this.excludedIds = nextSelected
          ? this.excludedIds.filter((id) => id !== itemId)
          : uniqueIds([...this.excludedIds, itemId])
      } else {
        this.selectedIds = nextSelected
          ? uniqueIds([...this.selectedIds, itemId])
          : this.selectedIds.filter((id) => id !== itemId)
        this.selectionTotal = this.selectedIds.length
      }
      this.invalidatePreview()
    },

    setPageSelection(itemIds: string[], selected: boolean) {
      const ids = uniqueIds(itemIds)
      if (!ids.length) return
      if (this.selectionMode === 'filter') {
        const pageIds = new Set(ids)
        this.excludedIds = selected
          ? this.excludedIds.filter((id) => !pageIds.has(id))
          : uniqueIds([...this.excludedIds, ...ids])
      } else {
        const selectedSet = new Set(this.selectedIds)
        ids.forEach((id) => (selected ? selectedSet.add(id) : selectedSet.delete(id)))
        this.selectedIds = [...selectedSet]
        this.selectionTotal = this.selectedIds.length
      }
      this.invalidatePreview()
    },

    async inspectDataset(request: TagEditorInspectRequest) {
      const requestVersion = ++inspectRequestVersion
      this.inspecting = true
      this.inspectError = ''
      try {
        const response = await apiClient.inspectTagEditorDataset(request)
        if (requestVersion !== inspectRequestVersion) return null

        itemsRequestVersion += 1
        detailRequestVersion += 1
        suggestionsRequestVersion += 1
        previewRequestVersion += 1
        changeRequestVersion += 1
        resultsRequestVersion += 1
        this.stopChangePolling()

        this.dataset = response.dataset
        this.lastInspectRequest = { ...request }
        this.items = response.items
        this.itemsTotal = response.dataset.total
        this.itemsOffset = 0
        this.itemsLimit = normalizePageSize(request.initialLimit ?? this.itemsLimit)
        this.query = ''
        this.itemState = 'all'
        this.sort = 'path_asc'
        this.commonTags = response.commonTags
        this.itemsLoading = false
        this.itemsError = ''

        this.activeItemId = ''
        this.activeItem = null
        this.detailLoading = false
        this.detailError = ''
        this.selectionMode = 'explicit'
        this.selectedIds = []
        this.excludedIds = []
        this.selectionQuery = ''
        this.selectionState = 'all'
        this.selectionTotal = 0
        this.tagSuggestions = []
        this.suggestionsLoading = false
        this.suggestionsError = ''
        this.pendingOperations = []
        this.preview = null
        this.previewScope = null
        this.previewing = false
        this.previewError = ''
        this.applyError = ''
        this.currentChangeId = ''
        this.currentChange = null
        this.changeResults = []
        this.changeResultsTotal = 0
        this.changeResultsOffset = 0
        this.changeError = ''
        this.resultsError = ''

        void this.loadChangeHistory({ silent: true })
        return response
      } catch (error) {
        if (requestVersion === inspectRequestVersion) this.inspectError = errorMessage(error)
        return null
      } finally {
        if (requestVersion === inspectRequestVersion) this.inspecting = false
      }
    },

    async rescanDataset() {
      if (!this.lastInspectRequest) return null
      return this.inspectDataset({ ...this.lastInspectRequest })
    },

    async loadItems(
      options: {
        offset?: number
        query?: string
        state?: TagEditorItemState
        sort?: TagEditorSort
        silent?: boolean
      } = {},
    ) {
      if (!this.dataset) return null
      const datasetId = this.dataset.id
      const requestVersion = ++itemsRequestVersion
      const offset = Math.max(0, options.offset ?? this.itemsOffset)
      const query = options.query ?? this.query
      const state = options.state ?? this.itemState
      const sort = options.sort ?? this.sort

      if (
        this.selectionMode === 'filter' &&
        (query !== this.selectionQuery || state !== this.selectionState)
      ) {
        this.clearSelection()
      }
      if (!options.silent) {
        itemsLoadingVersion = requestVersion
        this.itemsLoading = true
      }
      this.itemsError = ''

      try {
        const response = await apiClient.listTagEditorDatasetItems(datasetId, {
          offset,
          limit: this.itemsLimit,
          query,
          state,
          sort,
        })
        if (requestVersion !== itemsRequestVersion || this.dataset?.id !== datasetId) return null

        this.items = response.items
        this.itemsTotal = response.total
        this.itemsOffset = response.offset
        this.query = query
        this.itemState = state
        this.sort = sort
        if (this.dataset.revision !== response.revision) {
          this.dataset = { ...this.dataset, revision: response.revision }
          this.invalidatePreview()
        }
        if (this.selectionMode === 'filter') this.selectionTotal = response.total
        return response
      } catch (error) {
        if (requestVersion === itemsRequestVersion && this.dataset?.id === datasetId) {
          this.itemsError = errorMessage(error)
        }
        return null
      } finally {
        if (!options.silent && requestVersion === itemsLoadingVersion) this.itemsLoading = false
      }
    },

    setItemsPage(page: number) {
      const normalized = Math.max(1, Math.trunc(page || 1))
      return this.loadItems({ offset: (normalized - 1) * this.itemsLimit })
    },

    setItemsPageSize(size: number) {
      this.itemsLimit = normalizePageSize(size)
      return this.loadItems({ offset: 0 })
    },

    setFilters(filters: { query?: string; state?: TagEditorItemState; sort?: TagEditorSort }) {
      return this.loadItems({
        offset: 0,
        query: filters.query ?? this.query,
        state: filters.state ?? this.itemState,
        sort: filters.sort ?? this.sort,
      })
    },

    async loadItemDetail(itemId: string) {
      if (!this.dataset || !itemId) {
        this.clearActiveItem()
        return null
      }
      const datasetId = this.dataset.id
      const requestVersion = ++detailRequestVersion
      detailLoadingVersion = requestVersion
      this.activeItemId = itemId
      this.activeItem = null
      this.detailLoading = true
      this.detailError = ''
      try {
        const item = await apiClient.getTagEditorDatasetItem(datasetId, itemId)
        if (
          requestVersion !== detailRequestVersion ||
          this.dataset?.id !== datasetId ||
          this.activeItemId !== itemId
        ) {
          return null
        }
        this.activeItem = item
        const index = this.items.findIndex((candidate) => candidate.id === itemId)
        if (index >= 0) this.items[index] = item
        return item
      } catch (error) {
        if (requestVersion === detailRequestVersion && this.activeItemId === itemId) {
          this.detailError = errorMessage(error)
        }
        return null
      } finally {
        if (requestVersion === detailLoadingVersion) this.detailLoading = false
      }
    },

    clearActiveItem() {
      detailRequestVersion += 1
      this.activeItemId = ''
      this.activeItem = null
      this.detailLoading = false
      this.detailError = ''
    },

    async loadTagSuggestions(query = '', limit = 50) {
      if (!this.dataset) return null
      const datasetId = this.dataset.id
      const requestVersion = ++suggestionsRequestVersion
      suggestionsLoadingVersion = requestVersion
      this.suggestionsLoading = true
      this.suggestionsError = ''
      try {
        const response = await apiClient.suggestTagEditorTags(datasetId, { query, limit })
        if (requestVersion !== suggestionsRequestVersion || this.dataset?.id !== datasetId) {
          return null
        }
        this.tagSuggestions = response.suggestions
        if (!query.trim()) this.commonTags = response.suggestions
        return response
      } catch (error) {
        if (requestVersion === suggestionsRequestVersion && this.dataset?.id === datasetId) {
          this.suggestionsError = errorMessage(error)
        }
        return null
      } finally {
        if (requestVersion === suggestionsLoadingVersion) this.suggestionsLoading = false
      }
    },

    setPendingOperations(operations: TagEditorOperation[]) {
      this.pendingOperations = operations.map(cloneOperation)
      this.invalidatePreview()
    },

    addPendingOperation(operation: TagEditorOperation) {
      this.pendingOperations.push(cloneOperation(operation))
      this.invalidatePreview()
    },

    updatePendingOperation(index: number, operation: TagEditorOperation) {
      if (index < 0 || index >= this.pendingOperations.length) return
      this.pendingOperations[index] = cloneOperation(operation)
      this.invalidatePreview()
    },

    removePendingOperation(index: number) {
      if (index < 0 || index >= this.pendingOperations.length) return
      this.pendingOperations.splice(index, 1)
      this.invalidatePreview()
    },

    clearPendingOperations() {
      this.pendingOperations = []
      this.invalidatePreview()
    },

    stageItemText(itemId: string, text: string) {
      if (!itemId) return
      this.selectionMode = 'explicit'
      this.selectedIds = [itemId]
      this.excludedIds = []
      this.selectionQuery = ''
      this.selectionState = 'all'
      this.selectionTotal = 1
      this.pendingOperations = [{ type: 'set', text }]
      this.invalidatePreview()
    },

    async previewPendingChanges(options: { scope?: TagEditorScope; sampleLimit?: number } = {}) {
      if (!this.dataset) return null
      const datasetId = this.dataset.id
      const revision = this.dataset.revision
      const scope = options.scope ? cloneScope(options.scope) : this.selectionScope
      if (!scope) {
        this.previewError = '请先选择要修改的项目。'
        return null
      }
      if (!this.pendingOperations.length) {
        this.previewError = '请先添加至少一个编辑操作。'
        return null
      }

      const operations = this.pendingOperations.map(cloneOperation)
      const requestVersion = ++previewRequestVersion
      previewLoadingVersion = requestVersion
      this.previewing = true
      this.previewError = ''
      this.applyError = ''
      this.preview = null
      this.previewScope = null
      try {
        const response = await apiClient.previewTagEditorChanges(datasetId, {
          revision,
          scope,
          operations,
          sampleLimit: options.sampleLimit ?? 30,
        })
        if (
          requestVersion !== previewRequestVersion ||
          this.dataset?.id !== datasetId ||
          this.dataset.revision !== revision
        ) {
          return null
        }
        this.preview = response
        this.previewScope = scope
        this.currentChangeId = response.id
        this.currentChange = response
        this.upsertChange(response)
        return response
      } catch (error) {
        if (requestVersion === previewRequestVersion && this.dataset?.id === datasetId) {
          this.previewError = errorMessage(error)
        }
        return null
      } finally {
        if (requestVersion === previewLoadingVersion) this.previewing = false
      }
    },

    async applyPreview(backupExisting = true) {
      if (!this.dataset || !this.preview || this.applying) return null
      const datasetId = this.dataset.id
      const preview = this.preview
      this.applying = true
      this.applyError = ''
      try {
        const change = await apiClient.applyTagEditorChanges(datasetId, {
          changeSetId: preview.id,
          revision: preview.revision,
          backupExisting,
        })
        if (this.dataset?.id !== datasetId) return change

        this.currentChangeId = change.id
        this.currentChange = change
        this.upsertChange(change)
        if (change.resultRevision) {
          this.dataset = { ...this.dataset, revision: change.resultRevision }
        }
        this.pendingOperations = []
        this.preview = null
        this.previewScope = null
        this.selectionMode = 'explicit'
        this.selectedIds = []
        this.excludedIds = []
        this.selectionQuery = ''
        this.selectionState = 'all'
        this.selectionTotal = 0

        if (isFinishedChange(change)) {
          await Promise.all([
            this.loadItems({ offset: this.itemsOffset, silent: true }),
            this.loadChangeHistory({ silent: true }),
            this.loadTagSuggestions('', 100),
          ])
        } else {
          this.startChangePolling(change.id)
        }
        return change
      } catch (error) {
        if (this.dataset?.id === datasetId) this.applyError = errorMessage(error)
        return null
      } finally {
        this.applying = false
      }
    },

    upsertChange(change: TagEditorChangeSetSummary) {
      const index = this.changeHistory.findIndex((candidate) => candidate.id === change.id)
      if (index >= 0) this.changeHistory[index] = change
      else this.changeHistory.unshift(change)
      this.changeHistory.sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    },

    async loadChangeHistory(options: { limit?: number; silent?: boolean } = {}) {
      const requestVersion = ++historyRequestVersion
      if (!options.silent) {
        historyLoadingVersion = requestVersion
        this.historyLoading = true
      }
      this.historyError = ''
      try {
        const response = await apiClient.listTagEditorChanges(options.limit ?? 100)
        if (requestVersion !== historyRequestVersion) return null
        this.changeHistory = response.changes
        return response
      } catch (error) {
        if (requestVersion === historyRequestVersion) this.historyError = errorMessage(error)
        return null
      } finally {
        if (!options.silent && requestVersion === historyLoadingVersion) {
          this.historyLoading = false
        }
      }
    },

    async loadChangeDetail(changeSetId: string, options: { silent?: boolean } = {}) {
      if (!changeSetId) return null
      const requestVersion = ++changeRequestVersion
      if (this.currentChangeId && this.currentChangeId !== changeSetId) {
        this.stopChangePolling()
        this.currentChange = null
        this.changeResults = []
        this.changeResultsTotal = 0
        this.changeResultsOffset = 0
      }
      this.currentChangeId = changeSetId
      if (!options.silent) {
        changeLoadingVersion = requestVersion
        this.changeLoading = true
      }
      this.changeError = ''
      try {
        const change = await apiClient.getTagEditorChange(changeSetId)
        if (requestVersion !== changeRequestVersion || this.currentChangeId !== changeSetId) {
          return null
        }
        this.currentChange = change
        this.upsertChange(change)
        return change
      } catch (error) {
        if (requestVersion === changeRequestVersion && this.currentChangeId === changeSetId) {
          this.changeError = errorMessage(error)
        }
        return null
      } finally {
        if (!options.silent && requestVersion === changeLoadingVersion) {
          this.changeLoading = false
        }
      }
    },

    async refreshChange(changeSetId?: string) {
      const targetId = changeSetId || this.currentChangeId
      const current = this.currentChange
      const wasFinished = current?.id === targetId ? isFinishedChange(current) : false
      const change = await this.loadChangeDetail(targetId, { silent: true })
      if (!change || !this.dataset || change.datasetId !== this.dataset.id) return change
      if (change.resultRevision) this.dataset = { ...this.dataset, revision: change.resultRevision }
      if (!wasFinished && isFinishedChange(change)) {
        await Promise.all([
          this.loadItems({ offset: this.itemsOffset, silent: true }),
          this.loadChangeHistory({ silent: true }),
          this.loadTagSuggestions('', 100),
        ])
      }
      return change
    },

    async loadChangeResults(
      changeSetId?: string,
      options: { offset?: number; limit?: number; silent?: boolean } = {},
    ) {
      const targetId = changeSetId || this.currentChangeId
      if (!targetId) return null
      const requestVersion = ++resultsRequestVersion
      const offset = Math.max(0, options.offset ?? this.changeResultsOffset)
      const limit = normalizePageSize(options.limit ?? this.changeResultsLimit)
      if (!options.silent) {
        resultsLoadingVersion = requestVersion
        this.resultsLoading = true
      }
      this.resultsError = ''
      try {
        const response = await apiClient.listTagEditorChangeResults(targetId, { offset, limit })
        if (requestVersion !== resultsRequestVersion || this.currentChangeId !== targetId) {
          return null
        }
        this.changeResults = response.items
        this.changeResultsTotal = response.total
        this.changeResultsOffset = response.offset
        this.changeResultsLimit = response.limit
        return response
      } catch (error) {
        if (requestVersion === resultsRequestVersion && this.currentChangeId === targetId) {
          this.resultsError = errorMessage(error)
        }
        return null
      } finally {
        if (!options.silent && requestVersion === resultsLoadingVersion) {
          this.resultsLoading = false
        }
      }
    },

    async rollbackChange(changeSetId: string) {
      if (!changeSetId || this.rollingBackChangeId) return null
      this.rollingBackChangeId = changeSetId
      this.rollbackError = ''
      try {
        const change = await apiClient.rollbackTagEditorChange(changeSetId)
        this.upsertChange(change)
        this.currentChangeId = change.id
        this.currentChange = change
        if (this.dataset?.id === change.datasetId && change.resultRevision) {
          this.dataset = { ...this.dataset, revision: change.resultRevision }
        }
        if (this.dataset?.id === change.datasetId && isFinishedChange(change)) {
          await Promise.all([
            this.loadItems({ offset: this.itemsOffset, silent: true }),
            this.loadChangeHistory({ silent: true }),
            this.loadTagSuggestions('', 100),
          ])
        } else if (!isFinishedChange(change)) {
          this.startChangePolling(change.id)
        }
        return change
      } catch (error) {
        this.rollbackError = errorMessage(error)
        return null
      } finally {
        this.rollingBackChangeId = ''
      }
    },

    startChangePolling(changeSetId: string) {
      this.stopChangePolling()
      if (!changeSetId) return
      const pollVersion = ++changePollVersion
      let misses = 0
      this.currentChangeId = changeSetId
      this.changePolling = true

      const poll = async () => {
        if (pollVersion !== changePollVersion || this.currentChangeId !== changeSetId) return
        const change = await this.loadChangeDetail(changeSetId, { silent: true })
        if (pollVersion !== changePollVersion || this.currentChangeId !== changeSetId) return
        if (!change) {
          misses += 1
          if (misses >= 5) {
            this.stopChangePolling()
            return
          }
        } else {
          misses = 0
          if (isFinishedChange(change)) {
            const refreshes: Promise<unknown>[] = [
              this.loadChangeHistory({ silent: true }),
              this.loadChangeResults(changeSetId, { offset: 0, silent: true }),
            ]
            if (this.dataset?.id === change.datasetId) {
              if (change.resultRevision) {
                this.dataset = { ...this.dataset, revision: change.resultRevision }
              }
              refreshes.push(
                this.loadItems({ offset: this.itemsOffset, silent: true }),
                this.loadTagSuggestions('', 100),
              )
            }
            this.stopChangePolling()
            await Promise.all(refreshes)
            return
          }
        }
        changePollTimer = window.setTimeout(() => void poll(), CHANGE_POLL_INTERVAL)
      }

      changePollTimer = window.setTimeout(() => void poll(), CHANGE_POLL_INTERVAL)
    },

    stopChangePolling() {
      changePollVersion += 1
      if (changePollTimer !== undefined) {
        window.clearTimeout(changePollTimer)
        changePollTimer = undefined
      }
      this.changePolling = false
    },

    clearDataset() {
      inspectRequestVersion += 1
      itemsRequestVersion += 1
      detailRequestVersion += 1
      suggestionsRequestVersion += 1
      previewRequestVersion += 1
      historyRequestVersion += 1
      changeRequestVersion += 1
      resultsRequestVersion += 1
      this.stopChangePolling()
      this.$reset()
    },
  },
})
