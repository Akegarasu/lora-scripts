<script setup lang="ts">
import {
  FolderOpened,
  Refresh,
  Search,
  Setting,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'

import FilePicker from '@/components/FilePicker.vue'
import type {
  TagEditorChangeSetSummary,
  TagEditorDatasetItem,
  TagEditorInspectRequest,
  TagEditorItemState,
  TagEditorOperation,
  TagEditorPreviewResponse,
  TagEditorRoot,
  TagEditorScope,
  TagEditorSort,
} from '@/api/types'
import { useTagEditorStore } from '@/stores/tagEditor'

import BatchChangeDrawer from './components/BatchChangeDrawer.vue'
import ChangePreviewDialog from './components/ChangePreviewDialog.vue'
import ChangeSetHistory from './components/ChangeSetHistory.vue'
import TagEditorGallery from './components/TagEditorGallery.vue'
import TagEditorInspector from './components/TagEditorInspector.vue'

type PreviewWithWarnings = TagEditorPreviewResponse & { warnings?: string[] }

const editor = useTagEditorStore()
const pickerVisible = ref(false)
const batchVisible = ref(false)
const previewVisible = ref(false)
const historyPreviewVisible = ref(false)
const mobileInspectorVisible = ref(false)
const mobileEditing = ref(false)
const viewportWidth = ref(typeof window === 'undefined' ? 1200 : window.innerWidth)
const draftText = ref('')
const draftItemId = ref('')
const editorMode = ref<'tags' | 'text'>('tags')
const queryInput = ref('')
const stateInput = ref<TagEditorItemState>('all')
const sortInput = ref<TagEditorSort>('path_asc')
const searchTimer = ref<number | undefined>()
const previewBase = ref<PreviewWithWarnings | null>(null)
const source = reactive<{
  root: TagEditorRoot
  path: string
  recursive: boolean
  captionExtension: string
  maxImages: number
}>({
  root: 'train',
  path: '',
  recursive: true,
  captionExtension: '.txt',
  maxImages: 50000,
})

const isMobile = computed(() => viewportWidth.value <= 760)
const dataset = computed(() => editor.dataset)
// List payloads contain a deliberately bounded Caption preview. Only the detail
// endpoint is safe to use as an editable source of truth.
const activeItem = computed<TagEditorDatasetItem | null>(() => editor.activeItem)
const hasDraft = computed(
  () => !!activeItem.value && draftItemId.value === activeItem.value.id && draftText.value !== activeItem.value.captionText,
)
const hasStagedSingleChange = computed(
  () => editor.pendingOperations.length > 0 && editor.pendingOperations.every((operation) => operation.type === 'set'),
)
const hasUnsaved = computed(() => hasDraft.value || editor.pendingOperations.length > 0)
const pendingIds = computed(() => (hasDraft.value && draftItemId.value ? [draftItemId.value] : []))
const selectionScope = computed<TagEditorScope | null>(() => editor.selectionScope)
const previewForDialog = computed<PreviewWithWarnings | null>(() => {
  if (!previewBase.value) return null
  const current = editor.currentChange
  if (!current || current.id !== previewBase.value.id) return previewBase.value
  return { ...previewBase.value, ...current }
})
const sourceLabel = computed(() => (source.path.trim() ? source.path.trim() : '尚未选择数据集目录'))
const itemCountLabel = computed(() => {
  if (!dataset.value) return '扫描后显示统计'
  return `${dataset.value.total} 张图片 · ${dataset.value.withCaption} 已有 · ${dataset.value.missing} 缺失`
})
const scopeLabel = computed(() => {
  if (editor.selectionMode === 'filter') {
    return `当前筛选全部 ${editor.selectionCount} 项`
  }
  return editor.selectionCount ? `已选择 ${editor.selectionCount} 项` : '未选择图片'
})
const stateOptions: Array<{ label: string; value: TagEditorItemState }> = [
  { label: '全部图片', value: 'all' },
  { label: '已有 Caption', value: 'with' },
  { label: '缺失 Caption', value: 'missing' },
  { label: '空白 Caption', value: 'empty' },
  { label: '存在错误', value: 'errors' },
  { label: '重复内容', value: 'duplicate' },
]
const sortOptions: Array<{ label: string; value: TagEditorSort }> = [
  { label: '路径升序', value: 'path_asc' },
  { label: '路径降序', value: 'path_desc' },
  { label: 'Caption 升序', value: 'caption_asc' },
  { label: '最近修改', value: 'modified_desc' },
]

watch(
  () => editor.activeItemId,
  () => {
    if (!editor.activeItemId) {
      draftItemId.value = ''
      draftText.value = ''
      return
    }
    const item = editor.activeItem
    if (!item || item.id !== editor.activeItemId) return
    draftItemId.value = item.id
    draftText.value = item.captionText
  },
)

watch(
  () => editor.dataset?.id,
  () => {
    queryInput.value = editor.query
    stateInput.value = editor.itemState
    sortInput.value = editor.sort
  },
)

watch(
  () => source.root,
  (root, previousRoot) => {
    if (root !== previousRoot) source.path = ''
  },
)

watch(
  () => [editor.currentChange?.id, editor.currentChange?.state] as const,
  async ([changeId, state], previous) => {
    if (!changeId || changeId !== previewBase.value?.id || !state) return
    const terminalStates = [
      'completed',
      'partial',
      'failed',
      'rolled_back',
      'rollback_partial',
      'interrupted',
    ]
    if (!terminalStates.includes(state)) return
    if (previous?.[0] === changeId && previous?.[1] === state) return
    if (previewBase.value && editor.currentChange) {
      previewBase.value = { ...previewBase.value, ...editor.currentChange }
    }
    await editor.loadChangeResults(changeId, { offset: 0, limit: 100, silent: true })
    if (!draftItemId.value || !editor.dataset) return
    const detail = await editor.loadItemDetail(draftItemId.value)
    if (detail) {
      draftText.value = detail.captionText
      draftItemId.value = detail.id
    }
  },
)

watch(queryInput, (value) => {
  if (!dataset.value || value === editor.query) return
  if (searchTimer.value !== undefined) window.clearTimeout(searchTimer.value)
  searchTimer.value = window.setTimeout(() => {
    void editor.setFilters({ query: value, state: stateInput.value, sort: sortInput.value })
  }, 260)
})

watch([stateInput, sortInput], ([state, sort], previous) => {
  if (!dataset.value) return
  if (state === previous?.[0] && sort === previous?.[1]) return
  if (searchTimer.value !== undefined) window.clearTimeout(searchTimer.value)
  void editor.setFilters({ query: queryInput.value, state, sort })
})

function updateViewport() {
  viewportWidth.value = window.innerWidth
}

function makeInspectRequest(): TagEditorInspectRequest | null {
  if (!source.path.trim()) {
    ElMessage.warning('请先选择图片目录')
    return null
  }
  return {
    root: source.root,
    path: source.path.trim(),
    recursive: source.recursive,
    captionExtension: source.captionExtension,
    maxImages: source.maxImages,
    initialLimit: editor.itemsLimit,
  }
}

async function inspectDataset() {
  if (dataset.value && hasUnsaved.value) {
    try {
      await ElMessageBox.confirm('扫描其他数据集会清除当前未应用的修改，是否继续？', '确认扫描数据集', {
        confirmButtonText: '继续扫描',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  const request = makeInspectRequest()
  if (!request) return
  const response = await editor.inspectDataset(request)
  if (!response) return
  queryInput.value = ''
  stateInput.value = 'all'
  sortInput.value = 'path_asc'
  ElMessage.success(`已扫描 ${response.dataset.total} 张图片`)
  if (response.items.length) await activateItem(response.items[0], { force: true })
}

async function rescanDataset() {
  if (hasUnsaved.value) {
    try {
      await ElMessageBox.confirm('重新扫描会清除当前未预览的修改，是否继续？', '确认重新扫描', {
        confirmButtonText: '重新扫描',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  const request = makeInspectRequest()
  if (!request) return
  const response = await editor.inspectDataset(request)
  if (response?.items.length) await activateItem(response.items[0], { force: true })
}

async function activateItem(item: TagEditorDatasetItem, options: { force?: boolean } = {}) {
  if (!options.force && (hasDraft.value || hasStagedSingleChange.value) && draftItemId.value !== item.id) {
    try {
      await ElMessageBox.confirm('当前图片有未应用的单项变更，切换后会丢弃该变更预览。', '确认切换图片', {
        confirmButtonText: '切换并丢弃',
        cancelButtonText: '继续编辑',
        type: 'warning',
      })
    } catch {
      return
    }
    draftText.value = ''
    draftItemId.value = ''
    clearStagedSingleChange()
  }
  const detail = await editor.loadItemDetail(item.id)
  if (!detail) return
  draftItemId.value = detail.id
  draftText.value = detail.captionText
  const captionExtension = dataset.value?.captionExtension || source.captionExtension
  if (captionExtension === '.caption') editorMode.value = 'text'
  else if (captionExtension === '.tags') editorMode.value = 'tags'
  if (isMobile.value) {
    mobileEditing.value = false
    mobileInspectorVisible.value = true
  }
}

function clearStagedSingleChange() {
  if (!hasStagedSingleChange.value) return
  editor.clearPendingOperations()
  previewBase.value = null
  previewVisible.value = false
}

function updateDraftText(value: string) {
  if (value === draftText.value) return
  clearStagedSingleChange()
  draftText.value = value
}

function resetDraft() {
  if (!activeItem.value) return
  clearStagedSingleChange()
  draftText.value = activeItem.value.captionText
}

async function previewSingle() {
  if (!activeItem.value || !hasDraft.value) {
    ElMessage.warning('当前没有待应用的单项修改')
    return
  }
  if (editor.pendingOperations.some((operation) => operation.type !== 'set')) {
    ElMessage.warning('请先完成或清空批量操作序列')
    return
  }
  editor.stageItemText(activeItem.value.id, draftText.value)
  const response = await editor.previewPendingChanges({
    scope: { mode: 'include', includeIds: [activeItem.value.id] },
    sampleLimit: 1,
  })
  if (!response) {
    ElMessage.error(editor.previewError || '无法生成变更预览')
    return
  }
  previewBase.value = response
  previewVisible.value = true
}

function openBatchDrawer() {
  if (!editor.selectionScope) {
    ElMessage.warning('请先选择图片或选择当前筛选全部')
    return
  }
  if (hasStagedSingleChange.value) {
    ElMessage.warning('请先完成或放弃当前图片的单项变更预览，再开始批量处理')
    return
  }
  if (hasDraft.value) {
    ElMessage.warning('请先预览当前图片的单项修改，再开始批量处理')
    return
  }
  batchVisible.value = true
}

async function previewBatch() {
  if (!selectionScope.value) {
    ElMessage.warning('请先选择图片')
    return
  }
  if (!editor.pendingOperations.length) {
    ElMessage.warning('请先添加至少一个批量操作')
    return
  }
  const response = await editor.previewPendingChanges({ scope: selectionScope.value, sampleLimit: 30 })
  if (!response) {
    ElMessage.error(editor.previewError || '无法生成变更预览')
    return
  }
  previewBase.value = response
  batchVisible.value = false
  previewVisible.value = true
}

async function applyPreview(backupExisting: boolean) {
  const targetId = previewBase.value?.id
  if (!targetId) return
  const change = await editor.applyPreview(backupExisting)
  if (!change) {
    ElMessage.error(editor.applyError || '无法应用变更')
    return
  }
  previewBase.value = { ...(previewBase.value as PreviewWithWarnings), ...change }
  if (change.state === 'completed' || change.state === 'partial' || change.state === 'failed') {
    ElMessage[change.state === 'completed' ? 'success' : 'warning'](
      change.state === 'completed' ? 'Caption 变更已安全写入' : `变更已结束：${change.message || change.state}`,
    )
    if (draftItemId.value) {
      const detail = await editor.loadItemDetail(draftItemId.value)
      if (detail) {
        draftText.value = detail.captionText
        draftItemId.value = detail.id
      }
    }
  } else {
    ElMessage.info('变更已进入后台队列，状态会自动更新')
  }
}

async function refreshPreview() {
  const id = previewBase.value?.id
  if (!id) return
  const change = await editor.refreshChange(id)
  if (change) previewBase.value = { ...(previewBase.value as PreviewWithWarnings), ...change }
}

async function showChangeDetails(change: TagEditorChangeSetSummary) {
  const detail = await editor.loadChangeDetail(change.id)
  if (!detail) {
    ElMessage.error(editor.changeError || '无法读取变更状态')
    return
  }
  await editor.loadChangeResults(change.id, { offset: 0, limit: 100 })
  previewBase.value = { ...detail, diffs: [], issues: [] }
  historyPreviewVisible.value = true
}

async function handleHistoryDetails(change: TagEditorChangeSetSummary) {
  await showChangeDetails(change)
}

async function rollbackChange(change: TagEditorChangeSetSummary) {
  try {
    await ElMessageBox.confirm(
      `将按变更集 ${change.id} 的 manifest 恢复已写入文件；外部修改文件会保留为冲突。`,
      '确认回滚变更',
      { confirmButtonText: '确认回滚', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const result = await editor.rollbackChange(change.id)
  if (!result) {
    ElMessage.error(editor.rollbackError || '回滚失败')
    return
  }
  ElMessage.info(result.state === 'rolled_back' ? '回滚已完成' : '回滚任务已开始')
}

function clearSelection() {
  editor.clearSelection()
}

function togglePageSelection() {
  const ids = editor.items.filter((item) => item.writable && !item.error).map((item) => item.id)
  const selected = ids.length > 0 && ids.every((id) => editor.isItemSelected(id))
  editor.setPageSelection(ids, !selected)
}

function handlePageChange(page: number) {
  void editor.setItemsPage(page)
}

function handlePageSizeChange(size: number) {
  void editor.setItemsPageSize(size)
}

async function navigateItem(direction: -1 | 1) {
  if (!editor.items.length) return
  const index = editor.items.findIndex((item) => item.id === editor.activeItemId)
  if (index < 0) return
  const targetIndex = index + direction
  if (targetIndex >= 0 && targetIndex < editor.items.length) {
    await activateItem(editor.items[targetIndex])
    return
  }
  const nextPage = editor.currentPage + direction
  if (nextPage < 1 || nextPage > editor.pageCount) return
  await editor.setItemsPage(nextPage)
  const target = direction > 0 ? editor.items[0] : editor.items[editor.items.length - 1]
  if (target) await activateItem(target)
}

function onKeydown(event: KeyboardEvent) {
  if (event.isComposing) return
  const target = event.target as HTMLElement | null
  const editingField = !!target?.closest('input, textarea, [contenteditable="true"]')
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
    event.preventDefault()
    if (hasDraft.value) void previewSingle()
    return
  }
  if (editingField || event.altKey || event.ctrlKey || event.metaKey) return
  if (event.key === 'ArrowLeft') {
    event.preventDefault()
    void navigateItem(-1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    void navigateItem(1)
  }
}

function onBeforeUnload(event: BeforeUnloadEvent) {
  if (!hasUnsaved.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(async () => {
  if (!hasUnsaved.value) return true
  try {
    await ElMessageBox.confirm('当前仍有未预览的修改，确定离开吗？', '未保存修改', {
      confirmButtonText: '离开',
      cancelButtonText: '留下',
      type: 'warning',
    })
    return true
  } catch {
    return false
  }
})

onMounted(() => {
  window.addEventListener('resize', updateViewport, { passive: true })
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('beforeunload', onBeforeUnload)
  void editor.loadChangeHistory({ silent: true })
})

onBeforeUnmount(() => {
  if (searchTimer.value !== undefined) window.clearTimeout(searchTimer.value)
  window.removeEventListener('resize', updateViewport)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('beforeunload', onBeforeUnload)
  editor.stopChangePolling()
})
</script>

<template>
  <section class="tag-editor-page" aria-labelledby="tag-editor-title">
    <header class="page-header">
      <div class="page-heading">
        <div class="title-row">
          <h1 id="tag-editor-title">Caption 编辑器</h1>
          <span v-if="hasUnsaved" class="dirty-badge" aria-live="polite">有待应用修改</span>
        </div>
      </div>
    </header>

    <section class="source-section" aria-labelledby="source-title">
      <div class="source-heading">
        <div>
          <h2 id="source-title">选择并扫描 Caption 目录</h2>
          <p>只读取 train、datasets 或 workspace 根目录中的本地 sidecar。</p>
        </div>
        <div class="source-actions">
          <el-button v-if="dataset" text :icon="Refresh" :loading="editor.inspecting" @click="rescanDataset">重新扫描</el-button>
        </div>
      </div>

      <div class="source-grid">
        <label class="field">
          <span>安全根目录</span>
          <el-select v-model="source.root">
            <el-option label="train" value="train" />
            <el-option label="datasets" value="datasets" />
            <el-option label="workspace" value="workspace" />
          </el-select>
        </label>
        <label class="field field-wide">
          <span>图片目录</span>
          <el-input v-model="source.path" clearable :placeholder="sourceLabel">
            <template #append><el-button :icon="FolderOpened" @click="pickerVisible = true">浏览</el-button></template>
          </el-input>
        </label>
        <label class="field">
          <span>Caption 后缀</span>
          <el-select v-model="source.captionExtension">
            <el-option label=".txt" value=".txt" />
            <el-option label=".caption" value=".caption" />
            <el-option label=".tags" value=".tags" />
          </el-select>
        </label>
        <label class="field">
          <span>扫描上限</span>
          <el-input-number v-model="source.maxImages" :min="1" :max="50000" :step="1000" controls-position="right" />
        </label>
        <label class="option-card">
          <span><strong>扫描子文件夹</strong><small>跳过隐藏目录和符号链接。</small></span>
          <el-switch v-model="source.recursive" />
        </label>
        <div class="scan-action">
          <el-button type="primary" :icon="Search" :loading="editor.inspecting" :disabled="!source.path.trim()" @click="inspectDataset">扫描数据集</el-button>
          <span v-if="editor.inspectError" class="error-text"><el-icon><WarningFilled /></el-icon>{{ editor.inspectError }}</span>
        </div>
      </div>
    </section>

    <el-alert
      v-if="editor.itemsError"
      type="error"
      :title="editor.itemsError"
      :closable="false"
      show-icon
    />

    <template v-if="dataset">
      <section class="dataset-summary" aria-label="数据集统计">
        <div class="dataset-path"><span>当前数据集</span><strong :title="dataset.path">{{ dataset.path || '根目录' }}</strong></div>
        <div class="summary-stats">
          <span><strong>{{ dataset.total }}</strong> 图片</span>
          <span class="success"><strong>{{ dataset.withCaption }}</strong> 已有</span>
          <span class="info"><strong>{{ dataset.missing }}</strong> 缺失</span>
          <span class="warning"><strong>{{ dataset.empty }}</strong> 空白</span>
          <span class="danger"><strong>{{ dataset.errors }}</strong> 错误</span>
          <span><strong>{{ dataset.duplicates }}</strong> 重复</span>
        </div>
      </section>

      <section class="editor-toolbar" aria-label="筛选和编辑工具">
        <el-input v-model="queryInput" class="query-input" :prefix-icon="Search" clearable placeholder="搜索文件名、路径、Caption 或标签" aria-label="搜索图片和 Caption" />
        <el-select v-model="stateInput" aria-label="筛选 Caption 状态">
          <el-option v-for="option in stateOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-select v-model="sortInput" aria-label="排序图片">
          <el-option v-for="option in sortOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
        <el-radio-group v-model="editorMode" size="small" aria-label="默认编辑模式">
          <el-radio-button value="tags">标签</el-radio-button>
          <el-radio-button value="text">文本</el-radio-button>
        </el-radio-group>
        <el-button type="primary" :disabled="!editor.selectionScope" @click="openBatchDrawer">批量处理</el-button>
      </section>

      <div class="scope-line" aria-live="polite">
        <span>{{ itemCountLabel }} · 当前筛选 {{ editor.itemsTotal }} 项</span>
        <strong>{{ scopeLabel }}</strong>
        <span v-if="editor.previewError" class="error-text">{{ editor.previewError }}</span>
      </div>

      <section class="editor-layout">
        <main class="gallery-panel">
          <TagEditorGallery
            :items="editor.items"
            :total="editor.itemsTotal"
            :offset="editor.itemsOffset"
            :page-size="editor.itemsLimit"
            :loading="editor.itemsLoading"
            :active-id="editor.activeItemId"
            :selected-ids="editor.selectedIds"
            :all-filtered="editor.selectionMode === 'filter'"
            :excluded-ids="editor.excludedIds"
            :pending-ids="pendingIds"
            @activate="activateItem"
            @toggle="(item, checked) => editor.toggleItemSelection(item.id, checked)"
            @toggle-page="togglePageSelection"
            @select-filtered="editor.selectAllFiltered"
            @clear-selection="clearSelection"
            @page-change="handlePageChange"
            @page-size-change="handlePageSizeChange"
          />
        </main>

        <aside class="desktop-inspector">
          <TagEditorInspector
            :item="activeItem"
            :draft-text="draftText"
            :mode="editorMode"
            :common-tags="editor.commonTags"
            :loading="editor.detailLoading"
            :error="editor.detailError"
            :pending="hasDraft"
            @update:draft-text="updateDraftText"
            @update:mode="(value) => (editorMode = value)"
            @reset="resetDraft"
            @previous="() => navigateItem(-1)"
            @next="() => navigateItem(1)"
          />
          <div class="inspector-actions">
            <el-button :disabled="!hasDraft" @click="resetDraft">撤销本项修改</el-button>
            <el-button type="primary" :loading="editor.previewing" :disabled="!hasDraft" @click="previewSingle">预览单项写入</el-button>
          </div>
        </aside>
      </section>

      <div v-if="hasDraft" class="pending-bar" role="status" aria-live="polite">
        <div><span class="pending-dot" aria-hidden="true" /><strong>当前有 1 项单项修改</strong><span>尚未写入文件</span></div>
        <div><el-button @click="resetDraft">放弃修改</el-button><el-button type="primary" :loading="editor.previewing" @click="previewSingle">打开变更预览</el-button></div>
      </div>

    </template>

    <div v-else class="empty-workspace">
      <el-icon><Setting /></el-icon>
      <strong>扫描一个 Caption 数据集开始编辑</strong>
      <span>可先浏览图片；文件写入只会发生在确认变更预览之后。</span>
    </div>

    <ChangeSetHistory
      :changes="editor.changeHistory"
      :loading="editor.historyLoading"
      :error="editor.historyError"
      :rollback-id="editor.rollingBackChangeId"
      @refresh="() => editor.loadChangeHistory()"
      @details="handleHistoryDetails"
      @rollback="rollbackChange"
    />

    <FilePicker v-model="pickerVisible" kind="folder" :root="source.root" @select="(path) => (source.path = path)" />

    <BatchChangeDrawer
      v-model="batchVisible"
      :operations="editor.pendingOperations"
      :selected-count="editor.selectionCount"
      :all-filtered="editor.selectionMode === 'filter'"
      :pending-item-count="hasDraft ? 1 : 0"
      :loading="editor.previewing"
      @update:operations="editor.setPendingOperations"
      @preview="previewBatch"
    />

    <ChangePreviewDialog
      v-model="previewVisible"
      :preview="previewForDialog"
      :applying="editor.applying"
      :refreshing="editor.changeLoading"
      :results="editor.currentChangeId === previewBase?.id ? editor.changeResults : []"
      :results-total="editor.changeResultsTotal"
      :results-loading="editor.resultsLoading"
      :results-error="editor.resultsError"
      @apply="applyPreview"
      @refresh="refreshPreview"
    />
    <ChangePreviewDialog
      v-model="historyPreviewVisible"
      :preview="previewBase"
      :applying="false"
      :refreshing="editor.changeLoading"
      :results="editor.currentChangeId === previewBase?.id ? editor.changeResults : []"
      :results-total="editor.changeResultsTotal"
      :results-loading="editor.resultsLoading"
      :results-error="editor.resultsError"
      readonly
      @refresh="refreshPreview"
    />

    <el-drawer v-model="mobileInspectorVisible" class="mobile-inspector-drawer" title="Caption 编辑" direction="rtl" size="100%" :append-to-body="true" @closed="mobileEditing = false">
      <TagEditorInspector
        :item="activeItem"
        :draft-text="draftText"
        :mode="editorMode"
        :common-tags="editor.commonTags"
        :loading="editor.detailLoading"
        :error="editor.detailError"
        :readonly="!mobileEditing"
        :pending="hasDraft"
        @update:draft-text="updateDraftText"
        @update:mode="(value) => (editorMode = value)"
        @reset="resetDraft"
        @enable-edit="mobileEditing = true"
        @previous="() => navigateItem(-1)"
        @next="() => navigateItem(1)"
      />
      <template #footer>
        <div class="mobile-inspector-footer">
          <el-button :disabled="!hasDraft" @click="resetDraft">放弃修改</el-button>
          <el-button type="primary" :loading="editor.previewing" :disabled="!hasDraft" @click="previewSingle">预览单项写入</el-button>
        </div>
      </template>
    </el-drawer>
  </section>
</template>

<style scoped>
.tag-editor-page {
  width: min(100%, var(--page-max));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 30px clamp(20px, 3vw, 48px) 58px;
}

.page-header,
.title-row,
.source-heading,
.source-actions,
.dataset-summary,
.summary-stats,
.editor-toolbar,
.scope-line,
.pending-bar,
.pending-bar > div,
.inspector-actions,
.mobile-inspector-footer {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-header,
.source-heading,
.dataset-summary,
.scope-line,
.pending-bar {
  justify-content: space-between;
}

.page-header {
  align-items: flex-start;
  gap: 22px;
  margin-bottom: 22px;
}

.page-heading {
  min-width: 0;
}

.eyebrow,
.section-kicker,
.source-heading > div > span,
.dataset-path > span {
  color: var(--brand-strong);
  font-size: 12px;
  font-weight: 700;
}

.title-row {
  flex-wrap: wrap;
}

.page-heading h1 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: 30px;
  font-weight: 740;
}

.page-heading p {
  max-width: 780px;
  margin: 7px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.dirty-badge {
  padding: 4px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--warning-soft);
  color: var(--warning);
  font-size: 12px;
  font-weight: 650;
}

.source-section,
.dataset-summary,
.gallery-panel,
.desktop-inspector {
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface);
}

.source-section {
  display: grid;
  gap: 18px;
  padding: 10px 4px 28px;
}

.source-heading {
  align-items: flex-start;
  gap: 14px;
}

.source-heading > div:first-child {
  min-width: 0;
}

.source-heading h2 {
  margin: 3px 0 0;
  color: var(--text-strong);
  font-size: 18px;
}

.source-heading p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 13px;
}

.source-grid {
  display: grid;
  grid-template-columns: 180px minmax(260px, 1fr) 170px 150px;
  align-items: end;
  gap: 12px 14px;
}

.field,
.option-card {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.field > span,
.option-card strong {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 650;
}

.field-wide {
  grid-column: span 2;
}

.option-card {
  min-height: 40px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
}

.option-card > span {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.option-card small {
  color: var(--text-muted);
  font-size: 12px;
}

.scan-action {
  display: flex;
  align-items: center;
  gap: 10px;
}

.error-text {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--danger);
  font-size: 12px;
}

.dataset-summary {
  align-items: flex-start;
  gap: 16px;
  margin-top: 16px;
  padding: 14px 0;
}

.dataset-path {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.dataset-path strong {
  max-width: 420px;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.summary-stats {
  justify-content: flex-end;
  flex-wrap: wrap;
}

.summary-stats span {
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 12px;
}

.summary-stats strong {
  color: var(--text-strong);
}

.summary-stats .success strong { color: var(--success); }
.summary-stats .info strong { color: var(--info); }
.summary-stats .warning strong { color: var(--warning); }
.summary-stats .danger strong { color: var(--danger); }

.editor-toolbar {
  display: grid;
  grid-template-columns: minmax(200px, 1fr) 160px 150px auto auto;
  margin-top: 16px;
  padding: 10px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.query-input {
  min-width: 0;
}

.scope-line {
  min-height: 36px;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 12px;
}

.scope-line strong {
  color: var(--brand-strong);
  font-weight: 650;
}

.editor-layout {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 410px;
  align-items: start;
  gap: 16px;
}

.gallery-panel {
  min-width: 0;
  padding: 10px;
}

.desktop-inspector {
  position: sticky;
  top: 16px;
  min-width: 0;
  overflow: hidden;
}

.inspector-actions {
  justify-content: flex-end;
  padding: 0 18px 18px;
}

.pending-bar {
  position: sticky;
  z-index: 10;
  bottom: 14px;
  min-height: 56px;
  margin-top: 16px;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--warning) 30%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--surface) 94%, var(--warning-soft));
  box-shadow: var(--shadow-md);
}

.pending-bar > div:first-child {
  min-width: 0;
  flex-wrap: wrap;
  color: var(--text-muted);
  font-size: 12px;
}

.pending-bar strong {
  color: var(--text-strong);
  font-size: 13px;
}

.pending-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--warning);
}

.empty-workspace {
  min-height: 360px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 8px;
  margin-top: 16px;
  padding: 30px;
  border: 0;
  border-radius: 0;
  color: var(--text-muted);
  text-align: center;
}

.empty-workspace .el-icon {
  font-size: 34px;
}

.empty-workspace strong {
  color: var(--text-strong);
  font-size: 16px;
}

.mobile-inspector-footer {
  justify-content: flex-end;
}

@media (max-width: 1180px) {
  .editor-layout {
    grid-template-columns: minmax(0, 1fr) 360px;
  }

  .source-grid {
    grid-template-columns: 170px minmax(0, 1fr) 150px;
  }

  .source-grid .field-wide {
    grid-column: span 2;
  }

  .editor-toolbar {
    grid-template-columns: minmax(180px, 1fr) 150px 140px auto;
  }

  .editor-toolbar > :last-child {
    grid-column: 4;
  }
}

@media (max-width: 900px) {
  .editor-layout {
    grid-template-columns: 1fr;
  }

  .desktop-inspector {
    position: static;
  }

  .source-grid,
  .editor-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .source-grid .field-wide,
  .editor-toolbar .query-input {
    grid-column: 1 / -1;
  }
}

@media (max-width: 760px) {
  :global(.mobile-inspector-drawer) {
    width: 100vw !important;
    max-width: 100vw;
  }

  .tag-editor-page {
    padding: 20px 14px 88px;
  }

  .page-header,
  .source-heading,
  .dataset-summary,
  .pending-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .source-grid,
  .editor-toolbar {
    grid-template-columns: 1fr;
  }

  .source-grid .field-wide,
  .editor-toolbar .query-input,
  .editor-toolbar > :last-child {
    grid-column: auto;
  }

  .scan-action,
  .source-actions,
  .pending-bar > div {
    width: 100%;
  }

  .scan-action .el-button,
  .pending-bar > div:last-child .el-button {
    flex: 1;
  }

  .summary-stats {
    justify-content: flex-start;
  }

  .desktop-inspector {
    display: none;
  }

  .gallery-panel {
    padding: 6px;
  }

  .pending-bar {
    bottom: calc(72px + env(safe-area-inset-bottom));
  }

  .mobile-inspector-footer {
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding-bottom: env(safe-area-inset-bottom);
  }
}
</style>
