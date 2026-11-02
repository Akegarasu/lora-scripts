<script setup lang="ts">
import { computed } from 'vue'

import type { CaptionModelParam } from '@/api/types'
import ParameterHelp from '@/components/ParameterHelp.vue'

const props = defineProps<{
  param: CaptionModelParam
  modelValue: unknown
}>()

const emit = defineEmits<{
  'update:modelValue': [value: unknown]
}>()

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const numberValue = computed({
  get: () => (typeof props.modelValue === 'number' ? props.modelValue : Number(props.modelValue || 0)),
  set: (next: number | undefined) => emit('update:modelValue', next ?? props.param.default ?? 0),
})

const booleanValue = computed({
  get: () => Boolean(props.modelValue),
  set: (next: boolean) => emit('update:modelValue', next),
})

const textValue = computed({
  get: () => (props.modelValue === null || props.modelValue === undefined ? '' : String(props.modelValue)),
  set: (next: string) => emit('update:modelValue', next),
})

const supplementaryInfo = computed(() => {
  const parts: string[] = []
  if (props.param.description) parts.push(props.param.description)
  if (props.param.default !== undefined && props.param.default !== null && props.param.default !== '') {
    parts.push(`默认值：${formatValue(props.param.default)}`)
  }
  if (props.param.min !== undefined || props.param.max !== undefined) {
    parts.push(`范围：${props.param.min ?? '不限'} ～ ${props.param.max ?? '不限'}`)
  }
  if (props.param.step !== undefined) parts.push(`步长：${props.param.step}`)
  return parts.join('；')
})

function formatValue(value: unknown) {
  if (typeof value === 'boolean') return value ? '开启' : '关闭'
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

function choiceLabel(choice: unknown) {
  if (props.param.name === 'promptPreset') {
    const labels: Record<string, string> = {
      custom: '自定义指令',
      straightforward: '简洁描述',
      descriptive: '详细描述',
      training_prompt: '扩散模型训练 Prompt',
      booru: 'Booru 逗号标签',
    }
    return labels[String(choice)] || String(choice)
  }
  if (typeof choice === 'boolean') return choice ? '启用' : '关闭'
  if (choice === null || choice === undefined || choice === '') return '默认'
  return String(choice)
}
</script>

<template>
  <ParameterHelp v-if="param.type === 'boolean'" class="param-control" :content="supplementaryInfo" :label="`${param.label}说明`">
    <div class="boolean-control">
      <strong>{{ param.label }}</strong>
      <el-switch v-model="booleanValue" :aria-label="param.label" />
    </div>
  </ParameterHelp>

  <ParameterHelp v-else class="param-control" :content="supplementaryInfo" :label="`${param.label}说明`">
    <span class="param-label">
      <span>
        {{ param.label }}
        <em v-if="param.required">必填</em>
      </span>
    </span>

    <el-input-number
      v-if="param.type === 'integer' || param.type === 'number'"
      v-model="numberValue"
      :min="param.min"
      :max="param.max"
      :step="param.step || (param.type === 'integer' ? 1 : 0.01)"
      :precision="param.type === 'integer' ? 0 : undefined"
      controls-position="right"
      :aria-label="param.label"
    />

    <el-select
      v-else-if="param.type === 'choice'"
      v-model="value"
      filterable
      :aria-label="param.label"
      :placeholder="param.placeholder || `选择${param.label}`"
    >
      <el-option
        v-for="choice in param.choices || []"
        :key="String(choice)"
        :label="choiceLabel(choice)"
        :value="choice"
      />
    </el-select>

    <el-input
      v-else-if="param.type === 'multiline'"
      v-model="textValue"
      type="textarea"
      :rows="4"
      :maxlength="8000"
      show-word-limit
      :aria-label="param.label"
      :placeholder="param.placeholder"
    />

    <el-input
      v-else
      v-model="textValue"
      clearable
      :aria-label="param.label"
      :placeholder="param.placeholder"
    />

  </ParameterHelp>
</template>

<style scoped>
.param-control {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 7px;
}

.param-control :deep(.el-input-number) {
  width: 100%;
}

.param-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 640;
}

.param-label em {
  margin-left: 5px;
  color: var(--danger);
  font-size: 13px;
  font-style: normal;
}

.boolean-control {
  min-width: 0;
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0;
}

.boolean-control strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 640;
}
</style>
