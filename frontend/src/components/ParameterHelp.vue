<script setup lang="ts">
import { onBeforeUnmount, ref, useId, watch } from 'vue'

defineOptions({ inheritAttrs: false })

withDefaults(defineProps<{
  content: string
  label?: string
  as?: string
}>(), {
  label: '参数说明',
  as: 'div',
})

const descriptionId = `parameter-help-${useId()}`
const visible = ref(false)
const anchor = ref<HTMLElement>()
const tooltip = ref<{ onOpen: () => void; onClose: () => void; hide: () => void }>()

function onFocusOut(event: FocusEvent) {
  if ((event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) return
  tooltip.value?.onClose()
}

function dismissOnEscape(event: KeyboardEvent) {
  if (event.key !== 'Escape') return
  tooltip.value?.onClose()
  tooltip.value?.hide()
  visible.value = false
}

watch(visible, (open) => {
  if (open) document.addEventListener('keydown', dismissOnEscape, true)
  else document.removeEventListener('keydown', dismissOnEscape, true)
})

onBeforeUnmount(() => document.removeEventListener('keydown', dismissOnEscape, true))
</script>

<template>
  <component
    :is="as"
    ref="anchor"
    v-bind="$attrs"
    class="parameter-help"
    :role="$attrs.role || 'group'"
    :aria-label="$attrs['aria-label'] || label"
    :aria-describedby="content ? descriptionId : undefined"
    @focusin="tooltip?.onOpen()"
    @focusout="onFocusOut"
  >
    <slot />
    <span v-if="content" :id="descriptionId" class="parameter-help-description">{{ content }}</span>
    <el-tooltip
      ref="tooltip"
      v-model:visible="visible"
      :virtual-ref="anchor"
      virtual-triggering
      :disabled="!content"
      :content="content"
      :aria-label="label"
      :show-after="400"
      :hide-after="120"
      :trigger-keys="[]"
      placement="top-start"
      effect="light"
      enterable
      popper-class="parameter-help-popper"
    />
  </component>
</template>

<style scoped>
.parameter-help {
  min-width: 0;
}

.parameter-help-description {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
  border: 0;
}

:global(.parameter-help-popper) {
  max-width: min(420px, calc(100vw - 32px));
  padding: 12px 14px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-line;
}
</style>
