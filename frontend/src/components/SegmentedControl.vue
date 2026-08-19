<script setup lang="ts">
export interface SegmentedControlOption {
  label: string
  value: string
  disabled?: boolean
}

withDefaults(defineProps<{
  modelValue: string
  options: readonly SegmentedControlOption[]
  accessibleLabel: string
  disabled?: boolean
}>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>

<template>
  <div
    class="segmented-control"
    role="radiogroup"
    :aria-label="accessibleLabel"
    :aria-disabled="disabled || undefined"
    :style="{ gridTemplateColumns: `repeat(${options.length}, minmax(82px, 1fr))` }"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      role="radio"
      :class="{ active: modelValue === option.value }"
      :aria-checked="modelValue === option.value"
      :disabled="disabled || option.disabled"
      @click="emit('update:modelValue', option.value)"
    >
      {{ option.label }}
    </button>
  </div>
</template>

<style scoped>
.segmented-control {
  display: grid;
  max-width: 100%;
  padding: 3px;
  border-radius: 999px;
  background: var(--surface-sunken);
}

.segmented-control button {
  min-height: 34px;
  padding: 6px 18px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 140ms ease, background-color 140ms ease, box-shadow 140ms ease;
}

.segmented-control button:hover:not(:disabled) {
  color: var(--text-strong);
}

.segmented-control button:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--brand) 58%, transparent);
  outline-offset: -2px;
}

.segmented-control button.active {
  background: var(--surface);
  color: var(--text-strong);
  box-shadow: 0 1px 4px rgb(0 0 0 / 12%);
}

.segmented-control button:disabled {
  color: var(--text-muted);
  cursor: not-allowed;
  opacity: 0.58;
}

.segmented-control button.active:disabled {
  opacity: 0.78;
}
</style>
