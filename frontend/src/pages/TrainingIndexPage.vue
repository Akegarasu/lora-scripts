<script setup lang="ts">
const groups = [
  {
    title: "LoRA 训练",
    description: "只训练轻量增量权重，适合角色、画风和概念训练。",
    modes: [
      { title: "新手模式", detail: "精简常用参数，适合第一次配置 Stable Diffusion LoRA。", to: "/lora/basic.html", tag: "入门" },
      { title: "Stable Diffusion", detail: "完整配置 SD 1.5 与 SDXL LoRA、LyCORIS 和优化器参数。", to: "/lora/master.html", tag: "专家" },
      { title: "Flux LoRA", detail: "面向 Flux 模型的独立 Schema 与训练参数。", to: "/lora/flux.html", tag: "Flux" },
      { title: "Anima LoRA", detail: "Anima DiT 标准 LoRA 训练工作流。", to: "/lora/sd3.html", tag: "推荐" },
      { title: "Anima Fast", detail: "带独立环境安装、审计和 preflight 的高速训练流程。", to: "/lora/anima-fast.html", tag: "进阶" },
    ],
  },
  {
    title: "全量微调",
    description: "更新模型主体权重，需要更多显存、磁盘空间和训练时间。",
    modes: [
      { title: "Anima Finetune", detail: "Anima DiT 整模微调，适合高显存设备。", to: "/lora/anima-finetune.html", tag: "Anima" },
      { title: "Dreambooth", detail: "Stable Diffusion 全量训练入口，支持对应的动态 Schema。", to: "/dreambooth/index.html", tag: "SD" },
    ],
  },
] as const
</script>

<template>
  <div class="training-index-page">
    <header class="training-index-header">
      <span class="eyebrow">TRAINING WORKSPACE</span>
      <h1>选择训练模式</h1>
      <p>根据基础模型和训练目标进入对应配置页。每个入口都会加载后端 Schema，并保留各训练类型的草稿与历史。</p>
    </header>
    <section v-for="group in groups" :key="group.title" class="training-mode-group">
      <header><div><h2>{{ group.title }}</h2><p>{{ group.description }}</p></div><span>{{ group.modes.length }} 种模式</span></header>
      <div class="training-mode-grid">
        <RouterLink v-for="mode in group.modes" :key="mode.to" :to="mode.to" class="training-mode-card">
          <span>{{ mode.tag }}</span><h3>{{ mode.title }}</h3><p>{{ mode.detail }}</p><strong>配置训练 →</strong>
        </RouterLink>
      </div>
    </section>
  </div>
</template>
