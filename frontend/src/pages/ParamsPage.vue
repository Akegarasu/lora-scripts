<template>
  <article class="content-page">
    <header class="content-hero"><span class="eyebrow">TRAINING REFERENCE</span><h1>训练参数调节</h1><p>实际可用字段由当前训练页面的后端 Schema 决定。以下说明保留旧版最常用的调参原则。</p></header>
    <section><h2>模型与数据集</h2><h3>底模选择</h3><p>优先选择与目标模型架构一致、来源明确的基础模型。在融合模型上训练可能对该底模效果很好，但通常会降低 LoRA 在其他底模上的迁移性。</p><h3>训练分辨率</h3><p>应与模型原生分辨率及数据质量匹配。开启 bucket 后，不同比例图片会分配到相近尺寸桶；过高分辨率会显著增加显存和训练时间。</p></section>
    <section><h2>训练强度</h2><div class="content-table"><div><strong>Epoch / Step</strong><span>共同决定数据被学习的次数。先以预设为基线，观察样图再增减。</span></div><div><strong>Batch size</strong><span>增大批次通常更稳定但占用更多显存；不要只为追求速度超过设备能力。</span></div><div><strong>Learning rate</strong><span>过高容易破坏泛化与画面质量，过低则可能学习不足。不同优化器的合理范围不同。</span></div></div></section>
    <section><h2>网络与优化器</h2><p><code>network_dim</code> 决定 LoRA 容量，较高值可表达更多特征，也会增加文件大小和过拟合风险。LyCORIS、LoKr、DyLoRA 与基础 LoRA 参数并不完全互换。</p><p>AdamW、Prodigy、DAdaptation 等优化器对学习率有不同约定；选择预设后不要照搬另一优化器的学习率。界面会对已知冲突组合给出警告。</p></section>
    <section><h2>保存与预览</h2><p>设置合理保存间隔并启用样图预览，可以及早发现欠拟合、过拟合或 Caption 问题。正式提交前检查右侧 TOML，导出的配置会先经过后端规范化。</p></section>
  </article>
</template>
