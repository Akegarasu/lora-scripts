<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { ArrowDownBold, ArrowUpBold } from '@element-plus/icons-vue'

import {
  alternateNotation,
  modelNumberText,
  toScientificNotation,
  validateNumericInput,
} from '@/utils/scientificNumber'

const props = defineProps<{
  modelValue: unknown
  label: string
  placeholder?: string
  min?: number
  max?: number
  step?: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: number | null]
}>()

const inputRef = ref<HTMLInputElement>()
const rawText = ref(modelNumberText(props.modelValue))
const focused = ref(false)
const feedbackId = `scientific-number-${useId()}`

const validation = computed(() =>
  validateNumericInput(rawText.value, { min: props.min, max: props.max }),
)
const invalidMessage = computed(() =>
  validation.value.status === 'invalid' ? validation.value.message : '',
)
const conversion = computed(() => {
  const result = validation.value
  return result.status === 'valid' ? alternateNotation(rawText.value, result.value) : null
})
const stepAmount = computed(() =>
  props.step !== undefined && Number.isFinite(props.step) && props.step > 0 ? props.step : 1,
)
const stepBase = computed(() => {
  const result = validation.value
  if (result.status === 'valid') return result.value
  const modelValue = Number(props.modelValue)
  if (props.modelValue !== '' && props.modelValue !== null && Number.isFinite(modelValue)) return modelValue
  return props.min !== undefined && props.min > 0 ? props.min : 0
})
const canDecrease = computed(() => {
  const next = normalizedStep(stepBase.value - stepAmount.value)
  return Number.isFinite(next) && (props.min === undefined || next >= props.min)
})
const canIncrease = computed(() => {
  const next = normalizedStep(stepBase.value + stepAmount.value)
  return Number.isFinite(next) && (props.max === undefined || next <= props.max)
})

watch(
  () => props.modelValue,
  (next) => {
    const result = validation.value
    const nextNumber = Number(next)
    const isLocalValidUpdate =
      focused.value &&
      result.status === 'valid' &&
      next !== '' &&
      next !== null &&
      Number.isFinite(nextNumber) &&
      Object.is(result.value, nextNumber)
    const isLocalClear = focused.value && result.status === 'empty' && (next === null || next === '')
    if (!isLocalValidUpdate && !isLocalClear) rawText.value = modelNumberText(next)
  },
)

watch(
  invalidMessage,
  () => nextTick(() => inputRef.value?.setCustomValidity(invalidMessage.value)),
  { immediate: true },
)

function onInput(event: Event) {
  rawText.value = (event.target as HTMLInputElement).value
  const result = validation.value
  if (result.status === 'empty') emit('update:modelValue', null)
  if (result.status === 'valid') emit('update:modelValue', result.value)
}

function onBlur() {
  focused.value = false
  if (validation.value.status === 'invalid') {
    rawText.value = modelNumberText(props.modelValue)
    return
  }
  rawText.value = rawText.value.trim()
}

function finishEditing(event: KeyboardEvent) {
  if (validation.value.status === 'invalid') return
  ;(event.currentTarget as HTMLInputElement).blur()
}

function cancelEditing(event: KeyboardEvent) {
  rawText.value = modelNumberText(props.modelValue)
  ;(event.currentTarget as HTMLInputElement).blur()
}

function normalizedStep(value: number) {
  return Number(value.toPrecision(15))
}

function stepBy(direction: -1 | 1) {
  const next = normalizedStep(stepBase.value + direction * stepAmount.value)
  if (!Number.isFinite(next)) return
  if (props.min !== undefined && next < props.min) return
  if (props.max !== undefined && next > props.max) return

  const keepScientificNotation = /[eE]/.test(rawText.value)
  rawText.value = keepScientificNotation
    ? (toScientificNotation(String(next)) || String(next))
    : String(next)
  emit('update:modelValue', next)
  nextTick(() => inputRef.value?.focus())
}
</script>

<template>
  <div class="scientific-number-control">
    <div
      class="number-entry"
      :class="{ 'is-invalid': invalidMessage }"
    >
      <input
        ref="inputRef"
        class="number-input"
        type="text"
        inputmode="text"
        autocomplete="off"
        :value="rawText"
        :aria-label="label"
        :aria-describedby="feedbackId"
        :aria-invalid="!!invalidMessage"
        :placeholder="placeholder"
        @input="onInput"
        @focus="focused = true"
        @blur="onBlur"
        @keydown.enter.prevent="finishEditing"
        @keydown.esc.prevent="cancelEditing"
        @keydown.up.prevent="stepBy(1)"
        @keydown.down.prevent="stepBy(-1)"
      />
      <span class="number-steppers">
        <button
          type="button"
          class="step-button"
          :disabled="!canIncrease"
          :aria-label="`增大${label}`"
          @click="stepBy(1)"
        >
          <ArrowUpBold aria-hidden="true" />
        </button>
        <button
          type="button"
          class="step-button"
          :disabled="!canDecrease"
          :aria-label="`减小${label}`"
          @click="stepBy(-1)"
        >
          <ArrowDownBold aria-hidden="true" />
        </button>
      </span>
    </div>

    <span
      :id="feedbackId"
      class="number-feedback"
      :class="{ error: invalidMessage }"
      aria-live="polite"
    >
      <template v-if="invalidMessage">{{ invalidMessage }}</template>
      <template v-else-if="conversion">
        <span>{{ conversion.label }}</span>
        <code>{{ conversion.value }}</code>
      </template>
    </span>
  </div>
</template>

<style scoped>
.scientific-number-control {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 220px) minmax(0, 1fr);
  align-items: center;
  gap: 10px;
}

.number-entry {
  min-width: 0;
  height: 36px;
  display: flex;
  overflow: hidden;
  border-radius: 8px;
  background: var(--surface-raised);
  box-shadow: 0 0 0 1px var(--border) inset;
  transition: box-shadow 150ms ease, background-color 150ms ease;
}

.number-entry:hover {
  box-shadow: 0 0 0 1px var(--border-strong) inset;
}

.number-entry:focus-within {
  box-shadow: 0 0 0 1px var(--brand) inset, 0 0 0 2px color-mix(in srgb, var(--brand) 10%, transparent);
}

.number-entry.is-invalid {
  box-shadow: 0 0 0 1px var(--danger) inset, 0 0 0 2px color-mix(in srgb, var(--danger) 10%, transparent);
}

.number-input {
  min-width: 0;
  width: 100%;
  padding: 0 11px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-family: var(--font-mono);
  font-size: 14px;
  letter-spacing: 0;
}

.number-input:focus-visible {
  outline: none;
}

.number-input::placeholder {
  color: var(--text-muted);
  font-family: var(--font-sans);
}

.number-steppers {
  flex: 0 0 32px;
  display: grid;
  grid-template-rows: repeat(2, 1fr);
  margin: 1px 1px 1px 0;
  border-left: 1px solid var(--border-subtle);
}

.step-button {
  width: 31px;
  min-height: 0;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
}

.step-button:first-child {
  border-bottom: 1px solid var(--border-subtle);
}

.step-button:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.step-button:focus-visible {
  z-index: 1;
  outline: 2px solid color-mix(in srgb, var(--brand) 45%, transparent);
  outline-offset: -2px;
}

.step-button:disabled {
  color: var(--text-faint);
  cursor: not-allowed;
  opacity: 0.45;
}

.step-button svg {
  width: 11px;
  height: 11px;
}

.number-feedback {
  min-width: 0;
  min-height: 18px;
  display: flex;
  align-items: baseline;
  gap: 7px;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 18px;
  overflow-wrap: anywhere;
}

.number-feedback span {
  flex: 0 0 auto;
  font-size: 11px;
}

.number-feedback code {
  color: var(--text-secondary);
  font-size: 12px;
}

.number-feedback.error {
  color: var(--danger);
}

@media (max-width: 720px) {
  .scientific-number-control {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
}
</style>
