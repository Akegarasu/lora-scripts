<script setup lang="ts">
const portals = [
  { title: "标准 LoRA", text: "Stable Diffusion、Flux 与 Anima 的标准训练入口。", to: "/lora/index.html", tone: "blue" },
  { title: "Anima Fast", text: "独立运行环境、安装审计与高性能训练流程。", to: "/lora/anima-fast.html", tone: "cyan" },
  { title: "数据集工作台", text: "自动打标、Caption 清理、筛选和批量编辑。", to: "/native-tageditor.html", tone: "violet" },
] as const
</script>

<template>
  <div class="home-page">
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">LOCAL TRAINING WORKSPACE</span>
        <h1>模型训练，从一套清晰的工作流开始。</h1>
        <p>Next Trainer 将训练配置、数据集准备与运行监控集中在本地界面中。</p>
        <div class="hero-actions"><RouterLink class="primary-action" to="/lora/index.html">开始配置训练</RouterLink><RouterLink class="secondary-action" to="/help/guide.html">阅读使用指南</RouterLink></div>
      </div>
      <div class="hero-visual" aria-hidden="true"><div class="visual-grid" /><div class="orbit orbit-one" /><div class="orbit orbit-two" /><div class="core">N</div></div>
    </section>
    <section class="portal-grid" aria-label="功能入口">
      <RouterLink v-for="(portal, index) in portals" :key="portal.to" :to="portal.to" class="portal-card" :data-tone="portal.tone">
        <span class="portal-index">0{{ index + 1 }}</span><h2>{{ portal.title }}</h2><p>{{ portal.text }}</p><span class="portal-link">进入工作区 <b>→</b></span>
      </RouterLink>
    </section>
    <section class="status-strip"><span><i class="status-dot" /> 本地服务架构</span><span>Vue 3 重构进行中</span><span>旧前端已完整备份</span></section>
  </div>
</template>
