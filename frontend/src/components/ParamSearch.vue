<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { RefreshLeft, Search } from '@element-plus/icons-vue'

import type { ParamDefinition, ParamPriority } from '@/api/types'
import { useCatalogStore } from '@/stores/catalog'
import { useDraftStore } from '@/stores/draft'
import ParamControl from './ParamControl.vue'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const catalog = useCatalogStore()
const draft = useDraftStore()

const visible = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const query = ref('')
const priorityFilter = ref<ParamPriority | ''>('')
const groupFilter = ref('')
const modifiedOnly = ref(false)
const queryInputElement = ref<{ focus: () => void } | null>(null)

const PRIORITY_LABEL: Record<string, string> = {
  required: '必填',
  recommended: '推荐',
  advanced: '高级',
  dangerous: '危险',
  raw: '未分类',
  hidden: '隐藏',
}

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

function priorityTagType(priority: ParamPriority): TagType {
  if (priority === 'required' || priority === 'dangerous') return 'danger'
  if (priority === 'recommended') return 'success'
  return 'info'
}

const searchableParams = computed(() => catalog.allParams.filter((param) => !param.hidden))
const groupOptions = computed(() =>
  catalog.allGroups
    .map((group) => ({
      id: group.id,
      title: group.title,
      count: group.params.filter((param) => !param.hidden).length,
    }))
    .filter((group) => group.count > 0),
)
const results = computed(() => {
  const q = query.value.trim().toLowerCase()
  return searchableParams.value.filter((param) => {
    if (priorityFilter.value && param.priority !== priorityFilter.value) return false
    if (groupFilter.value && param.group !== groupFilter.value) return false
    if (modifiedOnly.value && !isModified(param)) return false
    if (!q) return true
    const source = param.source
      ? [param.source.script, param.source.module, param.source.function].filter(Boolean).join(' ')
      : ''
    return (
      param.name.toLowerCase().includes(q) ||
      (param.label || '').toLowerCase().includes(q) ||
      (param.description || '').toLowerCase().includes(q) ||
      (param.help || '').toLowerCase().includes(q) ||
      source.toLowerCase().includes(q)
    )
  })
})
const modifiedCount = computed(() => searchableParams.value.filter(isModified).length)
const resultModifiedCount = computed(() => results.value.filter(isModified).length)
const activeFilterCount = computed(
  () => Number(Boolean(query.value.trim())) + Number(Boolean(priorityFilter.value)) + Number(Boolean(groupFilter.value)) + Number(modifiedOnly.value),
)

function defaultHint(param: ParamDefinition) {
  const value = getDefaultValue(param)
  if (value === null || value === undefined || value === '') return '无默认值'
  if (typeof value === 'boolean') return `默认：${value ? '开启' : '关闭'}`
  if (Array.isArray(value)) return `默认：${value.join(', ')}`
  return `默认：${String(value)}`
}

function getDefaultValue(param: ParamDefinition) {
  return param.effectiveDefault ?? param.default
}

function isModified(param: ParamDefinition) {
  return draft.isValueModified(param)
}

function restoreDefault(param: ParamDefinition) {
  draft.resetValue(param)
}

function sourceHint(param: ParamDefinition) {
  if (!param.source) return ''
  return [param.source.script, param.source.module, param.source.function].filter(Boolean).join(' · ')
}

function clearFilters() {
  query.value = ''
  priorityFilter.value = ''
  groupFilter.value = ''
  modifiedOnly.value = false
}

async function focusSearchInput() {
  await nextTick()
  queryInputElement.value?.focus()
}
</script>

<template>
  <el-drawer
    v-model="visible"
    title="参数搜索"
    size="min(760px, 100vw)"
    :append-to-body="true"
    @opened="focusSearchInput"
  >
    <div class="search-toolbar" role="search" aria-label="筛选训练参数">
      <el-input
        ref="queryInputElement"
        v-model="query"
        class="query-input"
        :prefix-icon="Search"
        placeholder="搜索名称、标题、说明或来源"
        clearable
        aria-label="搜索参数"
      />
      <el-select v-model="groupFilter" placeholder="全部分组" clearable aria-label="按参数分组筛选">
        <el-option
          v-for="group in groupOptions"
          :key="group.id"
          :label="`${group.title} · ${group.count}`"
          :value="group.id"
        />
      </el-select>
      <el-select v-model="priorityFilter" placeholder="全部级别" clearable aria-label="按参数级别筛选">
        <el-option
          v-for="(label, key) in PRIORITY_LABEL"
          v-show="key !== 'hidden'"
          :key="key"
          :label="label"
          :value="key"
        />
      </el-select>
      <el-checkbox v-model="modifiedOnly">只看已修改</el-checkbox>
    </div>

    <div class="search-summary" role="status" aria-live="polite">
      <span>
        找到 <strong>{{ results.length }}</strong> / {{ searchableParams.length }} 个参数
        <template v-if="resultModifiedCount">，其中 {{ resultModifiedCount }} 个已修改</template>
      </span>
      <span class="summary-modified">当前草稿共修改 {{ modifiedCount }} 项</span>
      <el-button v-if="activeFilterCount" text :icon="RefreshLeft" @click="clearFilters">
        清除 {{ activeFilterCount }} 个筛选
      </el-button>
    </div>

    <div
      v-if="catalog.loading && searchableParams.length === 0"
      class="search-loading"
      role="status"
      aria-live="polite"
    >
      <span>正在加载参数目录…</span>
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else class="search-results" role="list" aria-label="参数搜索结果">
      <article
        v-for="param in results"
        :key="param.name"
        class="search-item"
        :class="{ 'is-modified': isModified(param) }"
        role="listitem"
        :aria-labelledby="`search-param-${param.name}`"
      >
        <div class="search-meta">
          <div class="search-title">
            <strong :id="`search-param-${param.name}`">{{ param.label || param.name }}</strong>
            <el-tag class="meta-tag" size="small" type="info" effect="plain">
              {{ catalog.groupTitles[param.group] || param.group }}
            </el-tag>
            <el-tag
              size="small"
              :type="priorityTagType(param.priority)"
              effect="plain"
            >
              {{ PRIORITY_LABEL[param.priority] || param.priority }}
            </el-tag>
            <el-tag v-if="param.deprecated" size="small" type="warning" effect="plain">
              已弃用
            </el-tag>
            <el-tag v-if="isModified(param)" size="small" type="primary" effect="light">已修改</el-tag>
          </div>
          <code>{{ param.name }}</code>
          <p v-if="param.description || param.help">{{ param.description || param.help }}</p>
          <span v-if="sourceHint(param)" class="search-source" :title="sourceHint(param)">
            来源：{{ sourceHint(param) }}
          </span>
          <div class="search-default">
            <span>{{ defaultHint(param) }}</span>
            <el-button
              text
              size="small"
              :icon="RefreshLeft"
              :disabled="!isModified(param)"
              :aria-label="`恢复 ${param.label || param.name} 的默认值`"
              @click="restoreDefault(param)"
            >
              {{ getDefaultValue(param) === undefined || getDefaultValue(param) === null ? '清空' : '恢复默认' }}
            </el-button>
          </div>
        </div>
        <div class="search-editor">
          <ParamControl
            :param="param"
            :model-value="draft.getValue(param)"
            @update:model-value="draft.setValue(param, $event)"
          />
        </div>
      </article>
      <el-empty v-if="results.length === 0" description="没有匹配的参数" />
    </div>
  </el-drawer>
</template>

<style scoped>
.search-toolbar {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(130px, 0.45fr) minmax(120px, 0.4fr) auto;
  align-items: center;
  gap: 10px;
}

.search-summary {
  display: flex;
  align-items: center;
  gap: 10px 16px;
  min-height: 42px;
  margin: 8px 0 2px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  color: var(--el-text-color-secondary, #687787);
  font-size: 12px;
}

.search-summary strong {
  color: var(--el-text-color-primary);
  font-size: 14px;
}

.summary-modified {
  margin-left: auto;
}

.search-results {
  display: grid;
  gap: 0;
}

.search-loading {
  display: grid;
  gap: 14px;
  padding: 18px 4px;
  color: var(--text-muted);
  font-size: 13px;
}

.search-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 0.72fr);
  gap: 18px;
  padding: 15px 10px 15px 12px;
  border-top: 1px solid var(--el-border-color-lighter, #edf0f3);
  border-left: 2px solid transparent;
  align-items: start;
}

.search-item:first-child {
  border-top: 0;
}

.search-item.is-modified {
  border-left-color: var(--brand);
  background: var(--brand-softer);
}

.search-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.search-title strong {
  font-size: 14px;
  font-weight: 650;
}

.search-meta code {
  display: block;
  margin-top: 4px;
  color: var(--el-text-color-secondary, #687787);
  font-size: 12px;
}

.search-meta p {
  margin: 6px 0 0;
  color: var(--el-text-color-secondary, #687787);
  font-size: 13px;
  line-height: 1.45;
}

.search-source {
  display: block;
  overflow: hidden;
  margin-top: 5px;
  color: var(--text-muted);
  font-family: var(--font-mono);
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.search-default {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 26px;
  margin-top: 5px;
  color: var(--text-muted);
  font-size: 13px;
}

.search-editor {
  min-width: 0;
}

.meta-tag {
  --ui-tag-color: var(--text-secondary);
  --ui-tag-background: var(--surface-sunken);
  --ui-tag-border: var(--border);
}

@media (max-width: 700px) {
  .search-toolbar {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .query-input {
    grid-column: 1 / -1;
  }

  .search-summary {
    align-items: flex-start;
    flex-wrap: wrap;
    padding: 8px 0;
  }

  .summary-modified {
    margin-left: 0;
  }

  .search-item {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 460px) {
  .search-toolbar {
    grid-template-columns: minmax(0, 1fr);
  }

  .query-input {
    grid-column: auto;
  }
}
</style>
