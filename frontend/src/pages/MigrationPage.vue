<script setup lang="ts">
defineProps<{ title: string; area: string; training?: boolean }>()
</script>

<template>
  <div v-if="training" class="training-layout">
    <section class="form-canvas">
      <div class="section-heading"><span>{{ area }}</span><h1>{{ title }}</h1><p>动态 Schema 表单正在迁移。此处先固定新版布局边界，避免以不完整表单提交训练任务。</p></div>
      <div v-for="item in ['训练用模型', '数据集配置', '训练参数']" :key="item" class="form-skeleton"><div class="skeleton-title">{{ item }}</div><div class="skeleton-row"><span /><b /></div><div class="skeleton-row"><span /><b /></div></div>
    </section>
    <aside class="control-panel">
      <div class="panel-copy"><span class="eyebrow">MIGRATION IN PROGRESS</span><h2>{{ title }}</h2><p>旧版行为仍保存在 <code>frontendbak</code>，迁移完成前禁用危险操作。</p></div>
      <section class="preview-panel"><header>参数预览</header><pre># Schema adapter pending
model_train_type = "{{ area }}"</pre></section>
      <button class="disabled-action" disabled>开始训练</button>
    </aside>
  </div>
  <div v-else class="migration-page">
    <span class="eyebrow">VUE 3 MIGRATION</span><h1>{{ title }}</h1><p>{{ area }}模块正在从旧构建产物迁移。页面入口和布局已建立，业务功能尚未启用。</p>
    <div class="migration-note"><strong>为什么暂时不可操作？</strong><span>为避免新界面调用不完整 API 或改变原有数据，本阶段只启用已经核对完成的功能。</span></div>
    <RouterLink class="secondary-action" to="/">返回首页</RouterLink>
  </div>
</template>
