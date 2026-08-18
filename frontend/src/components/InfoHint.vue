<script setup lang="ts">
withDefaults(
  defineProps<{
    content: string
    label?: string
    placement?: 'top' | 'top-start' | 'top-end' | 'bottom' | 'bottom-start' | 'bottom-end' | 'left' | 'right'
  }>(),
  {
    label: '更多信息',
    placement: 'top',
  },
)
</script>

<template>
  <el-tooltip
    :content="content"
    :placement="placement"
    :show-after="180"
    effect="light"
    popper-class="info-hint-popper"
  >
    <span
      class="info-hint"
      role="img"
      tabindex="0"
      :aria-label="`${label}：${content}`"
      @click.stop
    >i</span>
  </el-tooltip>
</template>

<style scoped>
.info-hint {
  width: 16px;
  height: 16px;
  flex: none;
  display: inline-grid;
  place-items: center;
  border: 1px solid currentColor;
  border-radius: 50%;
  color: var(--text-muted);
  font-family: Georgia, serif;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  line-height: 1;
  cursor: help;
  transition: color 120ms ease, background-color 120ms ease;
}

.info-hint:hover,
.info-hint:focus-visible {
  background: var(--surface-hover);
  color: var(--text-strong);
  outline: none;
}

:global(.info-hint-popper) {
  max-width: min(320px, calc(100vw - 24px));
  line-height: 1.55;
  overflow-wrap: anywhere;
}

@media (prefers-reduced-motion: reduce) {
  .info-hint {
    transition: none;
  }
}
</style>
