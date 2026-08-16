<script setup lang="ts">
import { Delete, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { computed, reactive, ref, watch } from 'vue'

import type { TagEditorOperation } from '@/api/types'

const props = defineProps<{
  modelValue: boolean
  operations: TagEditorOperation[]
  selectedCount: number
  allFiltered: boolean
  pendingItemCount: number
  loading: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'update:operations': [value: TagEditorOperation[]]
  preview: []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
const operationType = ref<'add' | 'remove' | 'replace' | 'normalize'>('add')
const tagText = ref('')
const replaceForm = reactive({
  find: '',
  replacement: '',
  regex: false,
  caseSensitive: false,
  wholeWord: false,
})
const normalizeForm = reactive({
  trimWhitespace: true,
  deduplicate: true,
  sort: false,
})

const hasEffectiveScope = computed(() => props.selectedCount > 0 || props.pendingItemCount > 0)

watch(operationType, () => {
  tagText.value = ''
})

function splitTags(value: string) {
  return value
    .split(/[\n,]/u)
    .map((tag) => tag.trim())
    .filter(Boolean)
}

function updateOperations(value: TagEditorOperation[]) {
  emit('update:operations', value)
}

function addOperation() {
  let operation: TagEditorOperation | null = null
  if (operationType.value === 'add' || operationType.value === 'remove') {
    const tags = splitTags(tagText.value)
    if (!tags.length) {
      ElMessage.warning('请先输入至少一个标签')
      return
    }
    operation = operationType.value === 'add'
      ? {
          type: 'add',
          mode: 'tags',
          values: tags,
          position: 'end',
          separator: ', ',
          deduplicate: true,
        }
      : {
          type: 'remove',
          mode: 'tags',
          values: tags,
          matchCase: false,
          wholeWord: true,
          separator: ', ',
        }
  } else if (operationType.value === 'replace') {
    if (!replaceForm.find) {
      ElMessage.warning('请输入要查找的内容')
      return
    }
    if (replaceForm.regex) {
      try {
        void new RegExp(replaceForm.find, replaceForm.caseSensitive ? 'u' : 'iu')
      } catch (error) {
        ElMessage.error(`正则表达式无效：${error instanceof Error ? error.message : String(error)}`)
        return
      }
    }
    operation = {
      type: 'replace',
      search: replaceForm.find,
      replacement: replaceForm.replacement,
      useRegex: replaceForm.regex,
      matchCase: replaceForm.caseSensitive,
      wholeWord: replaceForm.wholeWord,
    }
  } else {
    if (!normalizeForm.trimWhitespace && !normalizeForm.deduplicate && !normalizeForm.sort) {
      ElMessage.warning('请至少选择一个整理选项')
      return
    }
    operation = {
      type: 'normalize',
      mode: 'tags',
      separator: ', ',
      trim: normalizeForm.trimWhitespace,
      deduplicate: normalizeForm.deduplicate,
      sort: normalizeForm.sort ? 'alphabetical' : 'none',
      caseSensitive: false,
      replaceUnderscore: false,
    }
  }

  updateOperations([...props.operations, operation])
  tagText.value = ''
  replaceForm.find = ''
  replaceForm.replacement = ''
}

function removeOperation(index: number) {
  const next = [...props.operations]
  next.splice(index, 1)
  updateOperations(next)
}

function operationLabel(operation: TagEditorOperation) {
  if (operation.type === 'set') return '设置当前 Caption'
  if (operation.type === 'add') return `添加标签：${operation.values.join(', ')}`
  if (operation.type === 'remove') return `删除标签：${operation.values.join(', ')}`
  if (operation.type === 'replace') {
    return `${operation.useRegex ? '正则' : '文本'}替换：${operation.search} -> ${operation.replacement || '空'}`
  }
  const parts = [
    operation.trim ? '清理空白' : '',
    operation.deduplicate ? '去重' : '',
    operation.sort !== 'none' ? '排序' : '',
  ].filter(Boolean)
  return `整理标签：${parts.join('、')}`
}
</script>

<template>
  <el-drawer
    v-model="visible"
    class="batch-change-drawer"
    title="批量处理"
    size="min(620px, 100vw)"
    :append-to-body="true"
  >
    <div class="batch-content">
      <div class="scope-summary">
        <div>
          <span>作用范围</span>
          <strong>
            {{ allFiltered ? `当前筛选全部 ${selectedCount} 项` : `已选择 ${selectedCount} 项` }}
          </strong>
        </div>
        <el-tag v-if="pendingItemCount" type="warning">另有 {{ pendingItemCount }} 项手动修改</el-tag>
      </div>

      <el-alert
        v-if="!hasEffectiveScope"
        type="warning"
        title="请先选择要处理的图片"
        :closable="false"
        show-icon
      />

      <section class="operation-builder" aria-labelledby="operation-builder-title">
        <div class="section-heading">
          <div>
            <h3 id="operation-builder-title">添加结构化操作</h3>
          </div>
          <el-tag type="info">按顺序执行</el-tag>
        </div>

        <el-radio-group v-model="operationType" aria-label="批量操作类型">
          <el-radio-button value="add">添加</el-radio-button>
          <el-radio-button value="remove">删除</el-radio-button>
          <el-radio-button value="replace">替换</el-radio-button>
          <el-radio-button value="normalize">整理</el-radio-button>
        </el-radio-group>

        <div v-if="operationType === 'add' || operationType === 'remove'" class="operation-form">
          <label>
            <span>{{ operationType === 'add' ? '要添加的标签' : '要删除的标签' }}</span>
            <el-input
              v-model="tagText"
              type="textarea"
              :rows="4"
              placeholder="使用逗号或换行分隔"
              aria-label="批量标签列表"
            />
          </label>
        </div>

        <div v-else-if="operationType === 'replace'" class="operation-form replace-form">
          <label>
            <span>查找</span>
            <el-input v-model="replaceForm.find" :prefix-icon="Search" clearable />
          </label>
          <label>
            <span>替换为</span>
            <el-input v-model="replaceForm.replacement" clearable />
          </label>
          <div class="switch-grid">
            <label><span>正则表达式</span><el-switch v-model="replaceForm.regex" /></label>
            <label><span>区分大小写</span><el-switch v-model="replaceForm.caseSensitive" /></label>
            <label><span>整词匹配</span><el-switch v-model="replaceForm.wholeWord" /></label>
          </div>
        </div>

        <div v-else class="operation-form normalize-form">
          <label><span>清理首尾空白</span><el-switch v-model="normalizeForm.trimWhitespace" /></label>
          <label><span>标签去重</span><el-switch v-model="normalizeForm.deduplicate" /></label>
          <label><span>按字母排序</span><el-switch v-model="normalizeForm.sort" /></label>
        </div>

        <el-button :icon="Plus" @click="addOperation">加入操作序列</el-button>
      </section>

      <section class="operation-list" aria-labelledby="operation-list-title">
        <div class="section-heading">
          <div>
            <h3 id="operation-list-title">操作序列</h3>
          </div>
          <el-tag>{{ operations.length }} 项</el-tag>
        </div>

        <ol v-if="operations.length">
          <li v-for="(operation, index) in operations" :key="`${operation.type}-${index}`">
            <span class="operation-order">{{ index + 1 }}</span>
            <div>
              <strong>{{ operationLabel(operation) }}</strong>
            </div>
            <el-button
              circle
              text
              :icon="Delete"
              :aria-label="`删除第 ${index + 1} 个操作`"
              @click="removeOperation(index)"
            />
          </li>
        </ol>
        <el-empty v-else description="尚未添加批量操作" :image-size="70" />
      </section>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <span>预览不会写入文件</span>
        <div>
          <el-button @click="visible = false">关闭</el-button>
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!hasEffectiveScope || operations.length === 0"
            @click="emit('preview')"
          >
            预览批量变更
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<style scoped>
.batch-content {
  display: grid;
  gap: 18px;
}

.scope-summary,
.section-heading,
.drawer-footer,
.drawer-footer > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.scope-summary {
  padding: 2px 0 6px;
}

.scope-summary > div {
  display: grid;
  gap: 2px;
}

.scope-summary span,
.section-heading span,
.drawer-footer > span {
  color: var(--text-muted);
  font-size: 12px;
}

.scope-summary strong {
  color: var(--text-strong);
  font-size: 15px;
}

.operation-builder,
.operation-list {
  display: grid;
  gap: 14px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-subtle);
}

.section-heading h3 {
  margin: 2px 0 0;
  color: var(--text-strong);
  font-size: 16px;
}

.operation-form,
.operation-form > label {
  display: grid;
  gap: 7px;
}

.operation-form > label > span,
.switch-grid label > span,
.normalize-form label > span {
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 620;
}

.replace-form {
  grid-template-columns: 1fr 1fr;
}

.switch-grid {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.switch-grid label,
.normalize-form label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 9px 10px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
}

.normalize-form {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.operation-list ol {
  margin: 0;
  display: grid;
  gap: 7px;
  padding: 0;
  list-style: none;
}

.operation-list li {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 9px 10px;
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
}

.operation-order {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  background: var(--brand-soft);
  color: var(--brand-strong);
  font-size: 12px;
  font-weight: 700;
}

.operation-list li > div {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.operation-list strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.drawer-footer > div {
  justify-content: flex-end;
}

@media (max-width: 680px) {
  .replace-form,
  .switch-grid,
  .normalize-form {
    grid-template-columns: 1fr;
  }

  .drawer-footer {
    align-items: stretch;
    flex-direction: column;
  }

  .drawer-footer > div {
    display: grid;
    grid-template-columns: 1fr 1fr;
  }
}
</style>
