<script setup lang="ts">
import { computed, ref } from 'vue'
import { Document, FolderOpened } from '@element-plus/icons-vue'

import type { ParamDefinition } from '@/api/types'
import FilePicker from './FilePicker.vue'
import InfoHint from './InfoHint.vue'
import ScientificNumberInput from './ScientificNumberInput.vue'

const props = defineProps<{
  param: ParamDefinition
  modelValue: unknown
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const control = computed(() => {
  if (props.param.type === 'number' && ['input', 'number'].includes(props.param.control || '')) {
    return 'scientificNumber'
  }
  if (props.param.control === 'input' && props.param.type === 'integer') return 'number'
  return props.param.control || defaultControl(props.param)
})
const isArrayParam = computed(() => props.param.type === 'array')
const selectChoices = computed(() =>
  (props.param.choices || []).filter((choice) => choice !== null && choice !== undefined),
)
const allowsCustomChoice = computed(() => props.param.extra?.allowCustomChoice === true)
const arrayItemType = computed(() => {
  const direct = props.param.itemType
  const extra = props.param.extra?.itemType
  return typeof direct === 'string' ? direct : typeof extra === 'string' ? extra : ''
})
const isModelSource = computed(() => control.value === 'modelSource')
const isFileOrFolder = computed(() => control.value === 'fileOrFolder')
const isPathControl = computed(() =>
  ['path', 'file', 'folder', 'fileOrFolder', 'modelSource'].includes(control.value),
)
const pickerVisible = ref(false)
const pickerKind = computed(() => {
  if (control.value === 'folder') return 'folder'
  if (isModelSource.value || isFileOrFolder.value) return 'model'
  return props.param.fileKind || control.value
})
const pickerRoot = computed(() => {
  if (isModelSource.value) return 'models'
  if (props.param.fileKind === 'dataset') return 'train'
  if (props.param.fileKind === 'output') return 'output'
  if (['model', 'lora', 'vae'].includes(props.param.fileKind || '')) return 'models'
  return 'workspace'
})
const defaultValue = computed(() => props.param.effectiveDefault ?? props.param.default)
const hasDefault = computed(
  () => defaultValue.value !== undefined && defaultValue.value !== null && defaultValue.value !== '',
)
const fieldLabel = computed(() => props.param.label || props.param.name)
const controlPlaceholder = computed(() => {
  if (props.param.placeholder) return props.param.placeholder
  if (hasDefault.value) return `默认：${formatValue(defaultValue.value)}`
  if (isModelSource.value) return '输入模型仓库 ID，或选择本地模型'
  if (isFileOrFolder.value) return '选择或输入本地模型文件或文件夹'
  if (isPathControl.value) return control.value === 'folder' ? '选择或输入文件夹路径' : '选择或输入文件路径'
  return '留空使用训练器默认值'
})
const defaultHint = computed(() =>
  hasDefault.value ? `默认值：${formatValue(defaultValue.value)}` : '未设置时由训练器决定',
)
const pathHint = computed(() => {
  if (isModelSource.value) return '可填写本地模型路径或 Hugging Face 仓库 ID'
  if (isFileOrFolder.value) return '接受本地模型文件或文件夹'
  if (control.value === 'folder') return '接受文件夹路径'
  if (isPathControl.value) return '接受文件路径'
  return ''
})
const controlInfo = computed(() => [defaultHint.value, pathHint.value].filter(Boolean).join('；'))

// el-input-number needs `undefined` (not 0) to render an empty field, otherwise
// every optional number silently compiles to 0.
const numberValue = computed<number | undefined>(() => {
  const raw = props.modelValue
  if (raw === null || raw === undefined || raw === '') return undefined
  const parsed = Number(raw)
  return Number.isNaN(parsed) ? undefined : parsed
})
const numberMin = computed(() => readNumericMeta('min'))
const numberMax = computed(() => readNumericMeta('max'))
const numberStep = computed(() => {
  if (props.param.type === 'integer') return Math.max(1, readNumericMeta('step') ?? 1)

  const explicit = readNumericMeta('step')
  if (explicit !== undefined && explicit > 0) return explicit

  const reference = [numberValue.value, toFiniteNumber(defaultValue.value)]
    .find((candidate): candidate is number => candidate !== undefined && candidate !== 0)
  if (reference === undefined) {
    const name = props.param.name.toLowerCase()
    const isLearningRate = name === 'learning_rate' || name.endsWith('_lr') || name.endsWith('_learning_rate')
    return isLearningRate ? 0.000001 : 0.01
  }

  const magnitude = Math.abs(reference)
  if (magnitude >= 1) return 0.1
  return 10 ** Math.floor(Math.log10(magnitude))
})
const numberPrecision = computed(() => {
  if (props.param.type === 'integer') return 0

  const explicit = readNumericMeta('precision')
  if (explicit !== undefined) return Math.min(12, Math.max(0, Math.trunc(explicit)))

  return Math.min(
    12,
    Math.max(
      decimalPlaces(numberStep.value),
      decimalPlaces(numberValue.value),
      decimalPlaces(toFiniteNumber(defaultValue.value)),
    ),
  )
})

const stringArrayText = computed(() =>
  Array.isArray(props.modelValue) ? (props.modelValue as unknown[]).join('\n') : String(props.modelValue ?? ''),
)

function defaultControl(param: ParamDefinition) {
  if (param.choices?.length) return 'select'
  if (param.type === 'boolean') return 'switch'
  if (param.type === 'integer') return 'number'
  if (param.type === 'number') return 'scientificNumber'
  if (param.type === 'array') return 'stringArray'
  if (param.type === 'path') return 'path'
  return 'input'
}

function readNumericMeta(key: 'min' | 'max' | 'step' | 'precision') {
  const direct = props.param[key]
  const extra = props.param.extra?.[key]
  return toFiniteNumber(direct ?? extra)
}

function toFiniteNumber(raw: unknown): number | undefined {
  if (raw === '' || raw === null || raw === undefined) return undefined
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : undefined
}

function decimalPlaces(raw: number | undefined) {
  if (raw === undefined || !Number.isFinite(raw)) return 0
  const text = String(raw).toLowerCase()
  if (text.includes('e-')) {
    const [coefficient, exponent] = text.split('e-')
    return Math.min(12, Number(exponent) + (coefficient.split('.')[1]?.length || 0))
  }
  return Math.min(12, text.split('.')[1]?.length || 0)
}

function formatValue(raw: unknown) {
  if (Array.isArray(raw)) return raw.join(', ')
  if (typeof raw === 'boolean') return raw ? '开启' : '关闭'
  if (typeof raw === 'object' && raw !== null) return JSON.stringify(raw)
  return String(raw)
}

function updateNumber(next: number | null | undefined) {
  value.value = next ?? null
}

function updateStringArray(next: string) {
  value.value = next
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
    .map(castArrayItem)
}

function updateSelect(next: unknown) {
  if (isArrayParam.value && Array.isArray(next)) {
    value.value = next.map(castArrayItem)
    return
  }
  value.value = castSelectItem(next)
}

function castSelectItem(item: unknown) {
  if (!['integer', 'number'].includes(props.param.type)) return item
  if (item === '' || item === null || item === undefined || typeof item === 'number') return item
  const parsed = Number(item)
  if (!Number.isFinite(parsed)) return item
  if (props.param.type === 'integer' && !Number.isInteger(parsed)) return item
  return parsed
}

function choiceLabel(choice: unknown) {
  const labels = props.param.extra?.choiceLabels
  if (labels && typeof labels === 'object' && !Array.isArray(labels)) {
    const label = (labels as Record<string, unknown>)[String(choice)]
    if (typeof label === 'string') return label
  }
  return String(choice)
}

function castArrayItem(item: unknown) {
  if (!['integer', 'number'].includes(arrayItemType.value)) return item
  if (typeof item === 'number') {
    return item
  }

  const text = String(item).trim()
  if (!text) return text
  const parsed = Number(text)
  if (!Number.isFinite(parsed)) return text
  if (arrayItemType.value === 'integer' && !Number.isInteger(parsed)) return text
  return parsed
}

function updatePath(next: string) {
  value.value = next
}
</script>

<template>
  <div class="param-control">
    <div class="control-row">
      <div class="control-input">
        <el-switch
          v-if="control === 'switch'"
          v-model="value"
          :aria-label="fieldLabel"
          inline-prompt
        />

        <el-select
          v-else-if="control === 'select'"
          :model-value="value"
          clearable
          filterable
          :allow-create="allowsCustomChoice"
          :default-first-option="allowsCustomChoice"
          :multiple="isArrayParam"
          :collapse-tags="isArrayParam"
          :collapse-tags-tooltip="isArrayParam"
          :aria-label="fieldLabel"
          :placeholder="controlPlaceholder"
          @update:model-value="updateSelect"
        >
          <el-option
            v-for="choice in selectChoices"
            :key="String(choice)"
            :label="choiceLabel(choice)"
            :value="choice"
          />
        </el-select>

        <el-input-number
          v-else-if="control === 'number'"
          class="number-control"
          :model-value="numberValue"
          :aria-label="fieldLabel"
          :min="numberMin"
          :max="numberMax"
          :precision="numberPrecision"
          :step="numberStep"
          :placeholder="controlPlaceholder"
          controls-position="right"
          @update:model-value="updateNumber"
        />

        <ScientificNumberInput
          v-else-if="control === 'scientificNumber'"
          :model-value="modelValue"
          :label="fieldLabel"
          :min="numberMin"
          :max="numberMax"
          :step="numberStep"
          :placeholder="controlPlaceholder"
          @update:model-value="updateNumber"
        />

        <div v-else-if="isPathControl" class="path-control">
          <el-input v-model="value" clearable :aria-label="fieldLabel" :placeholder="controlPlaceholder">
            <template #prefix>
              <el-icon aria-hidden="true">
                <FolderOpened v-if="control === 'folder'" />
                <Document v-else />
              </el-icon>
            </template>
            <template #append>
              <el-button :aria-label="`浏览${fieldLabel}`" @click="pickerVisible = true">浏览</el-button>
            </template>
          </el-input>
        </div>

        <el-input
          v-else-if="control === 'stringArray'"
          :model-value="stringArrayText"
          type="textarea"
          :aria-label="fieldLabel"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :placeholder="hasDefault ? `${controlPlaceholder}；每行一个值` : '每行一个值'"
          @update:model-value="updateStringArray"
        />

        <el-input
          v-else-if="control === 'textarea' || control === 'code'"
          v-model="value"
          type="textarea"
          :aria-label="fieldLabel"
          :autosize="{ minRows: 2, maxRows: 10 }"
          :placeholder="controlPlaceholder"
        />

        <el-input
          v-else-if="control === 'secret'"
          v-model="value"
          type="password"
          show-password
          clearable
          :aria-label="fieldLabel"
          :placeholder="controlPlaceholder"
        />

        <el-input v-else v-model="value" clearable :aria-label="fieldLabel" :placeholder="controlPlaceholder" />
      </div>
      <InfoHint :content="controlInfo" :label="`${fieldLabel}的默认与输入信息`" />
    </div>
  </div>

  <FilePicker
    v-if="isPathControl"
    v-model="pickerVisible"
    :kind="pickerKind"
    :root="pickerRoot"
    :allow-directories="isModelSource || isFileOrFolder"
    @select="updatePath"
  />
</template>

<style scoped>
.param-control {
  min-width: 0;
}

.control-row {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
}

.control-input {
  min-width: 0;
}

.control-input :deep(.el-select),
.control-input :deep(.el-input),
.control-input :deep(.el-textarea) {
  width: 100%;
}

.number-control {
  width: min(220px, 100%);
}

.path-control {
  min-width: 0;
}

@media (max-width: 720px) {
  .number-control {
    width: 100%;
  }
}
</style>
