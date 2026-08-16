<script setup lang="ts">
import {
  ArrowLeft,
  ArrowRight,
  Delete,
  Plus,
  RefreshLeft,
  RefreshRight,
  View,
  WarningFilled,
} from '@element-plus/icons-vue'
import { ElAutocomplete, ElImageViewer } from 'element-plus'
import { computed, nextTick, ref, watch } from 'vue'

import { apiAssetUrl } from '@/api/client'
import type { TagEditorItem } from '@/api/types'

const props = defineProps<{
  item: TagEditorItem | null
  draftText: string
  mode: 'tags' | 'text'
  commonTags: Array<{ text: string; count: number }>
  loading: boolean
  error?: string
  readonly?: boolean
  pending?: boolean
}>()

const emit = defineEmits<{
  'update:draftText': [value: string]
  'update:mode': [value: 'tags' | 'text']
  reset: []
  previous: []
  next: []
  'enable-edit': []
}>()

const tagInput = ref('')
const viewerVisible = ref(false)
const previewFailed = ref(false)
const undoStack = ref<string[]>([])
const redoStack = ref<string[]>([])
const textInput = ref<{ focus?: () => void } | null>(null)

const tags = computed(() => parseTags(props.draftText))
const existingTagSet = computed(() => new Set(tags.value.map((tag) => tag.toLowerCase())))
const quickTags = computed(() =>
  props.commonTags.filter((tag) => !existingTagSet.value.has(tag.text.toLowerCase())).slice(0, 12),
)
const canEdit = computed(
  () => !!props.item?.writable && !props.item?.error && !props.item?.sourceTruncated && !props.readonly,
)
const dirty = computed(() => !!props.item && props.draftText !== props.item.captionText)
const previewUrl = computed(() => {
  if (!props.item?.thumbnailUrl || previewFailed.value) return ''
  const separator = props.item.thumbnailUrl.includes('?') ? '&' : '?'
  return apiAssetUrl(`${props.item.thumbnailUrl}${separator}size=2048`)
})

watch(
  () => props.item?.id,
  () => {
    tagInput.value = ''
    undoStack.value = []
    redoStack.value = []
    viewerVisible.value = false
    previewFailed.value = false
  },
)

function parseTags(text: string) {
  return text
    .split(/[\n,]/u)
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function pushUpdate(value: string) {
  if (!canEdit.value || value === props.draftText) return
  undoStack.value.push(props.draftText)
  if (undoStack.value.length > 100) undoStack.value.shift()
  redoStack.value = []
  emit('update:draftText', value)
}

function updateRawText(value: string) {
  pushUpdate(value)
}

function addTag(value = tagInput.value) {
  const nextTag = value.trim().replace(/^,+|,+$/g, '').trim()
  if (!nextTag || existingTagSet.value.has(nextTag.toLowerCase())) {
    tagInput.value = ''
    return
  }
  pushUpdate([...tags.value, nextTag].join(', '))
  tagInput.value = ''
}

function removeTag(index: number) {
  const next = [...tags.value]
  next.splice(index, 1)
  pushUpdate(next.join(', '))
}

function fetchSuggestions(query: string, callback: (items: Array<{ value: string; count: number }>) => void) {
  const normalized = query.trim().toLowerCase()
  const candidates = props.commonTags
    .filter((tag) => !existingTagSet.value.has(tag.text.toLowerCase()))
    .filter((tag) => !normalized || tag.text.toLowerCase().includes(normalized))
    .slice(0, 20)
    .map((tag) => ({ value: tag.text, count: tag.count }))
  callback(candidates)
}

function selectSuggestion(entry: Record<string, unknown>) {
  if (typeof entry.value === 'string') addTag(entry.value)
}

function undo() {
  if (!canEdit.value) return
  const previous = undoStack.value.pop()
  if (previous === undefined) return
  redoStack.value.push(props.draftText)
  emit('update:draftText', previous)
}

function redo() {
  if (!canEdit.value) return
  const next = redoStack.value.pop()
  if (next === undefined) return
  undoStack.value.push(props.draftText)
  emit('update:draftText', next)
}

function reset() {
  if (!props.item || !dirty.value) return
  undoStack.value.push(props.draftText)
  redoStack.value = []
  emit('reset')
}

async function focusEditor() {
  await nextTick()
  textInput.value?.focus?.()
}

defineExpose({ undo, redo, focusEditor })
</script>

<template>
  <aside class="item-inspector" aria-label="当前 Caption 编辑器">
    <div v-if="loading" class="inspector-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <div v-else-if="error" class="inspector-error">
      <el-alert
        type="error"
        title="无法读取当前图片详情"
        :description="error"
        :closable="false"
        show-icon
      />
    </div>

    <div v-else-if="item" class="inspector-content">
      <header class="inspector-header">
        <div>
          <h2 :title="item.relativePath">{{ item.name }}</h2>
          <p :title="item.relativePath">{{ item.relativePath }}</p>
        </div>
        <el-tag v-if="pending || dirty" type="warning">待应用</el-tag>
        <el-tag v-else-if="item.error" type="danger">不可编辑</el-tag>
        <el-tag v-else type="info">扫描版本</el-tag>
      </header>

      <button
        class="preview-button"
        type="button"
        :disabled="!previewUrl"
        :aria-label="`查看 ${item.name} 大图`"
        @click="viewerVisible = true"
      >
        <img v-if="previewUrl" :src="previewUrl" :alt="item.name" @error="previewFailed = true" />
        <span v-else>图片不可用</span>
        <span v-if="previewUrl" class="preview-action"><el-icon><View /></el-icon> 查看大图</span>
      </button>

      <el-alert
        v-if="item.error"
        type="error"
        :title="item.error"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="item.sourceTruncated"
        type="warning"
        title="Caption 正文超过安全编辑上限"
        description="当前只提供只读预览，避免用不完整正文覆盖原文件。"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="!item.writable"
        type="warning"
        title="该 Caption 当前不可写"
        :closable="false"
        show-icon
      />
      <el-alert
        v-else-if="readonly"
        type="info"
        title="移动端当前为只读浏览"
        :closable="false"
        show-icon
      >
        <template #default>
          <el-button size="small" @click="emit('enable-edit')">启用此项编辑</el-button>
        </template>
      </el-alert>

      <div class="editor-toolbar">
        <el-radio-group
          :model-value="mode"
          size="small"
          :disabled="!canEdit"
          aria-label="编辑模式"
          @update:model-value="(value: string | number | boolean) => emit('update:mode', value as 'tags' | 'text')"
        >
          <el-radio-button value="tags">标签</el-radio-button>
          <el-radio-button value="text">自然语言</el-radio-button>
        </el-radio-group>

        <div class="history-actions">
          <el-tooltip content="撤销" placement="top">
            <el-button
              circle
              size="small"
              :icon="RefreshLeft"
              :disabled="!canEdit || undoStack.length === 0"
              aria-label="撤销本项编辑"
              @click="undo"
            />
          </el-tooltip>
          <el-tooltip content="重做" placement="top">
            <el-button
              circle
              size="small"
              :icon="RefreshRight"
              :disabled="!canEdit || redoStack.length === 0"
              aria-label="重做本项编辑"
              @click="redo"
            />
          </el-tooltip>
          <el-tooltip content="恢复扫描版本" placement="top">
            <el-button
              circle
              size="small"
              :icon="Delete"
              :disabled="!canEdit || !dirty"
              aria-label="恢复扫描时的 Caption"
              @click="reset"
            />
          </el-tooltip>
        </div>
      </div>

      <section v-if="mode === 'tags'" class="tag-editor" aria-label="标签编辑">
        <div class="tag-chips">
          <el-tag
            v-for="(tag, index) in tags"
            :key="`${tag}-${index}`"
            :closable="canEdit"
            type="info"
            @close="removeTag(index)"
          >
            {{ tag }}
          </el-tag>
          <span v-if="tags.length === 0" class="empty-tags">当前没有标签</span>
        </div>

        <ElAutocomplete
          v-model="tagInput"
          :fetch-suggestions="fetchSuggestions"
          :disabled="!canEdit"
          clearable
          placeholder="输入标签"
          aria-label="输入并补全标签"
          @select="selectSuggestion"
          @keyup.enter.prevent="addTag()"
        >
          <template #suffix><el-icon><Plus /></el-icon></template>
          <template #default="{ item: suggestion }">
            <span>{{ suggestion.value }}</span>
            <small>{{ suggestion.count }}</small>
          </template>
        </ElAutocomplete>

        <div v-if="quickTags.length" class="quick-tags" aria-label="常用标签">
          <span>常用</span>
          <button
            v-for="tag in quickTags"
            :key="tag.text"
            type="button"
            :disabled="!canEdit"
            @click="addTag(tag.text)"
          >
            <el-icon><Plus /></el-icon>{{ tag.text }}
          </button>
        </div>
      </section>

      <section v-else class="text-editor" aria-label="自然语言 Caption 编辑">
        <el-input
          ref="textInput"
          :model-value="draftText"
          type="textarea"
          :rows="10"
          resize="vertical"
          :disabled="!canEdit"
          placeholder="输入自然语言 Caption"
          aria-label="Caption 正文"
          @update:model-value="updateRawText"
        />
      </section>

      <div class="editor-status" aria-live="polite">
        <span v-if="dirty"><el-icon><WarningFilled /></el-icon> 修改尚未应用</span>
        <span v-else>与扫描版本一致</span>
        <span>{{ draftText.length }} 字符<template v-if="mode === 'tags'"> · {{ tags.length }} 个标签</template></span>
      </div>

      <details class="source-text">
        <summary>查看扫描版本</summary>
        <pre>{{ item.captionText || '无 Caption 内容' }}</pre>
      </details>

      <footer class="navigation-actions">
        <el-button :icon="ArrowLeft" @click="emit('previous')">上一张</el-button>
        <el-button @click="emit('next')">下一张<el-icon class="el-icon--right"><ArrowRight /></el-icon></el-button>
      </footer>
    </div>

    <div v-else class="inspector-empty">
      <el-icon><View /></el-icon>
      <strong>选择一张图片</strong>
      <span>Caption 和标签会显示在这里。</span>
    </div>

    <ElImageViewer
      v-if="viewerVisible && previewUrl"
      :url-list="[previewUrl]"
      :z-index="2700"
      teleported
      hide-on-click-modal
      @close="viewerVisible = false"
    />
  </aside>
</template>

<style scoped>
.item-inspector {
  min-width: 0;
  border-left: 0;
  background: var(--surface);
}

.inspector-content,
.inspector-loading,
.inspector-error {
  display: grid;
  gap: 15px;
  padding: 18px;
}

.inspector-error {
  min-height: 220px;
  align-content: center;
}

.inspector-header {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.inspector-header > div {
  min-width: 0;
}

.section-kicker {
  color: var(--brand-strong);
  font-size: 12px;
  font-weight: 700;
}

.inspector-header h2 {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 17px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-header p {
  margin: 3px 0 0;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-button {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  overflow: hidden;
  padding: 0;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--surface-sunken);
  color: var(--text-muted);
  cursor: zoom-in;
}

.preview-button img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.preview-action {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 8px;
  border-radius: 6px;
  background: rgb(18 18 18 / 72%);
  color: white;
  font-size: 12px;
}

.editor-toolbar,
.history-actions,
.editor-status,
.navigation-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.editor-toolbar,
.editor-status,
.navigation-actions {
  justify-content: space-between;
}

.tag-editor,
.text-editor {
  min-width: 0;
  display: grid;
  gap: 10px;
}

.tag-chips {
  min-height: 112px;
  max-height: 240px;
  display: flex;
  align-content: flex-start;
  flex-wrap: wrap;
  gap: 6px;
  overflow: auto;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-raised);
}

.empty-tags {
  color: var(--text-muted);
  font-size: 13px;
}

.quick-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.quick-tags > span {
  color: var(--text-muted);
  font-size: 12px;
}

.quick-tags button {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 7px;
  border: 0;
  border-radius: 6px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.quick-tags button:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--brand-strong);
}

.editor-status {
  color: var(--text-muted);
  font-size: 12px;
}

.editor-status > span:first-child {
  display: flex;
  align-items: center;
  gap: 5px;
}

.editor-status > span:first-child:has(.el-icon) {
  color: var(--warning);
}

.source-text {
  border-top: 1px solid var(--border-subtle);
  padding-top: 10px;
}

.source-text summary {
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.source-text pre {
  max-height: 180px;
  margin: 9px 0 0;
  overflow: auto;
  padding: 9px;
  border-radius: 7px;
  background: var(--surface-sunken);
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.navigation-actions .el-button {
  flex: 1;
}

.inspector-empty {
  min-height: 420px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 7px;
  padding: 20px;
  color: var(--text-muted);
  text-align: center;
}

.inspector-empty .el-icon {
  font-size: 30px;
}

.inspector-empty strong {
  color: var(--text-strong);
  font-size: 15px;
}

@media (max-width: 760px) {
  .item-inspector {
    border-left: 0;
  }

  .inspector-content,
  .inspector-loading,
  .inspector-error {
    padding: 12px 14px calc(82px + env(safe-area-inset-bottom));
  }

  .preview-button {
    aspect-ratio: 4 / 3;
  }

  .navigation-actions {
    position: sticky;
    z-index: 3;
    bottom: calc(64px + env(safe-area-inset-bottom));
    padding: 8px 0;
    background: var(--surface);
  }
}
</style>
