<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  CircleCheckFilled,
  CircleCloseFilled,
  Close,
  Cpu,
  Loading,
  Monitor,
  Moon,
  Refresh,
  Sunny,
} from '@element-plus/icons-vue'

import type { GpuInfo } from '@/api/types'
import { useDevicesStore } from '@/stores/devices'
import { useSettingsStore } from '@/stores/settings'

const props = withDefaults(defineProps<{ modal?: boolean }>(), {
  modal: false,
})
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const devices = useDevicesStore()
const refreshingAll = ref(false)
const activeSection = ref<'general' | 'service' | 'devices'>('general')

const serviceOnline = computed(
  () => !settings.healthError && settings.health?.status === 'ok',
)

const serviceLabel = computed(() => {
  if (settings.loadingHealth && !settings.health) return '正在检测'
  return serviceOnline.value ? '服务在线' : '服务离线'
})

const serviceDescription = computed(() => {
  if (settings.loadingHealth) return '正在与本地 Mikazuki 服务通信…'
  if (settings.healthError) return '无法连接后端，请确认服务已启动并检查 API 地址。'
  if (serviceOnline.value) return '训练、编译与任务接口均可访问。'
  return '服务返回了非正常状态，请刷新后重试。'
})

const isRefreshing = computed(
  () => refreshingAll.value || settings.loadingHealth || devices.loading,
)

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 GB'
  return `${(value / 1024 / 1024 / 1024).toFixed(1)} GB`
}

function gpuUsed(gpu: GpuInfo) {
  return Math.max(0, gpu.vramTotal - gpu.vramFree)
}

function gpuUsagePercent(gpu: GpuInfo) {
  if (!Number.isFinite(gpu.vramTotal) || gpu.vramTotal <= 0) return 0
  return Math.round(Math.min(100, Math.max(0, (gpuUsed(gpu) / gpu.vramTotal) * 100)))
}

function gpuUsageTone(gpu: GpuInfo) {
  const usage = gpuUsagePercent(gpu)
  if (usage >= 90) return 'is-critical'
  if (usage >= 75) return 'is-warning'
  return ''
}

async function refreshAll() {
  if (refreshingAll.value) return
  refreshingAll.value = true
  try {
    await Promise.allSettled([settings.loadHealth(), devices.loadGpus()])
  } finally {
    refreshingAll.value = false
  }
}

onMounted(() => {
  if (!settings.health && !settings.loadingHealth) void settings.loadHealth()
  if (!devices.loading) void devices.loadGpus()
})
</script>

<template>
  <section class="settings-page" :class="{ 'is-modal': props.modal }" aria-labelledby="settings-title">
    <header class="page-header">
      <div class="page-heading">
        <h1 id="settings-title">设置</h1>
      </div>

      <div class="header-actions">
        <div class="service-summary" role="status" aria-live="polite">
          <span
            class="status-dot"
            :class="{
              'is-online': serviceOnline,
              'is-pending': settings.loadingHealth,
            }"
            aria-hidden="true"
          />
          <span>
            <strong>{{ serviceLabel }}</strong>
            <small>{{ settings.health?.version || 'Mikazuki API' }}</small>
          </span>
        </div>
        <el-button
          text
          :icon="Refresh"
          :loading="isRefreshing"
          :disabled="isRefreshing"
          aria-label="刷新服务和显卡状态"
          @click="refreshAll"
        >
          刷新状态
        </el-button>
        <el-button
          v-if="props.modal"
          text
          circle
          :icon="Close"
          aria-label="关闭设置"
          title="关闭设置"
          @click="emit('close')"
        />
      </div>
    </header>

    <div class="settings-workspace">
      <nav class="settings-nav" aria-label="设置分类">
        <button :class="{ active: activeSection === 'general' }" type="button" @click="activeSection = 'general'">
          <Sunny /><span>常规</span>
        </button>
        <button :class="{ active: activeSection === 'service' }" type="button" @click="activeSection = 'service'">
          <Monitor /><span>后端服务</span>
        </button>
        <button :class="{ active: activeSection === 'devices' }" type="button" @click="activeSection = 'devices'">
          <Cpu /><span>计算设备</span>
        </button>
      </nav>

      <div class="settings-content">
      <aside v-if="activeSection === 'general'" class="settings-panel appearance-panel" aria-labelledby="appearance-title">
        <div class="settings-section-title"><h2 id="appearance-title">常规</h2></div>
        <div class="setting-row">
          <span><strong>外观</strong></span>
          <div class="theme-segment" role="group" aria-label="选择界面主题">
            <button :class="{ active: settings.theme === 'light' }" type="button" @click="settings.setTheme('light')"><Sunny />浅色</button>
            <button :class="{ active: settings.theme === 'dark' }" type="button" @click="settings.setTheme('dark')"><Moon />深色</button>
          </div>
        </div>
      </aside>

      <article v-else-if="activeSection === 'service'" class="settings-panel service-panel" aria-labelledby="service-title">
        <div class="panel-header">
          <div class="panel-title">
            <span class="panel-icon service-icon" aria-hidden="true">
              <Monitor />
            </span>
            <span>
              <h2 id="service-title">后端服务</h2>
              <p>{{ serviceDescription }}</p>
            </span>
          </div>
          <span
            class="status-badge"
            :class="{ online: serviceOnline, pending: settings.loadingHealth }"
          >
            <el-icon aria-hidden="true">
              <Loading v-if="settings.loadingHealth" class="spin" />
              <CircleCheckFilled v-else-if="serviceOnline" />
              <CircleCloseFilled v-else />
            </el-icon>
            {{ serviceLabel }}
          </span>
        </div>

        <div v-if="settings.healthError" class="inline-message error" role="alert">
          <CircleCloseFilled aria-hidden="true" />
          <div>
            <strong>连接失败</strong>
            <p>{{ settings.healthError }}</p>
          </div>
        </div>

        <dl class="service-facts">
          <div class="fact">
            <dt>服务版本</dt>
            <dd>{{ settings.health?.version || '—' }}</dd>
          </div>
          <div class="fact">
            <dt>Python</dt>
            <dd>{{ settings.health?.python || '—' }}</dd>
          </div>
          <div class="fact">
            <dt>运行模式</dt>
            <dd>
              <span
                v-if="settings.health"
                class="mode-chip"
                :class="{ development: settings.health.devMode }"
              >
                {{ settings.health.devMode ? '开发模式' : '生产模式' }}
              </span>
              <span v-else>—</span>
            </dd>
          </div>
          <div class="fact">
            <dt>API 地址</dt>
            <dd><code>{{ settings.apiBase }}</code></dd>
          </div>
        </dl>
      </article>

      <article v-else class="settings-panel gpu-panel" aria-labelledby="gpu-title">
        <div class="panel-header">
          <div class="panel-title">
            <span class="panel-icon gpu-icon" aria-hidden="true">
              <Cpu />
            </span>
            <span>
              <h2 id="gpu-title">计算设备</h2>
            </span>
          </div>
          <div class="gpu-header-status" aria-live="polite">
            <span v-if="devices.loading">
              <el-icon class="spin" aria-hidden="true"><Loading /></el-icon>
              正在检测
            </span>
            <span v-else-if="devices.gpus.length">
              {{ devices.gpus.length }} 张 GPU 可用
            </span>
            <el-button
              text
              :icon="Refresh"
              :loading="devices.loading"
              :disabled="devices.loading"
              aria-label="刷新显卡状态"
              @click="devices.loadGpus"
            >
              刷新
            </el-button>
          </div>
        </div>

        <div v-if="devices.error" class="inline-message warning" role="alert">
          <CircleCloseFilled aria-hidden="true" />
          <div>
            <strong>显卡检测不可用</strong>
            <p>{{ devices.error }}</p>
          </div>
        </div>

        <div
          v-if="devices.loading && devices.gpus.length === 0 && !devices.error"
          class="gpu-loading"
          role="status"
        >
          <span class="loading-orbit" aria-hidden="true"><Cpu /></span>
          <div>
            <strong>正在读取 CUDA 设备</strong>
          </div>
        </div>

        <div
          v-else-if="devices.gpus.length === 0 && !devices.error"
          class="empty-state"
          role="status"
        >
          <span class="empty-icon" aria-hidden="true"><Cpu /></span>
          <strong>未检测到可用 GPU</strong>
          <p>当前环境可能为 CPU 模式，或 CUDA 尚未对 PyTorch 可见。</p>
          <el-button :icon="Refresh" :loading="devices.loading" @click="devices.loadGpus">
            重新检测
          </el-button>
        </div>

        <ul v-else-if="devices.gpus.length" class="gpu-list" aria-label="可用显卡">
          <li
            v-for="gpu in devices.gpus"
            :key="gpu.id"
            class="gpu-card"
            :class="gpuUsageTone(gpu)"
          >
            <div class="gpu-card-heading">
              <div>
                <span class="gpu-index">GPU {{ gpu.id }}</span>
                <h3>{{ gpu.name }}</h3>
              </div>
              <strong class="usage-value">{{ gpuUsagePercent(gpu) }}%</strong>
            </div>

            <div
              class="memory-meter"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="gpuUsagePercent(gpu)"
              :aria-label="`GPU ${gpu.id} 显存已使用 ${gpuUsagePercent(gpu)}%`"
            >
              <span :style="{ width: `${gpuUsagePercent(gpu)}%` }" />
            </div>

            <div class="memory-legend">
              <span><strong>{{ formatBytes(gpuUsed(gpu)) }}</strong> 已使用</span>
              <span><strong>{{ formatBytes(gpu.vramFree) }}</strong> 可用</span>
              <span><strong>{{ formatBytes(gpu.vramTotal) }}</strong> 总计</span>
            </div>
          </li>
        </ul>
      </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.settings-page {
  width: min(100%, var(--page-max));
  min-height: 100dvh;
  margin: 0 auto;
  padding: 42px clamp(22px, 3.2vw, 54px) 64px;
}

.settings-page.is-modal {
  width: 100%;
  min-height: 0;
  margin: 0;
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

.settings-page.is-modal .settings-workspace {
  min-height: min(680px, 70dvh);
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 28px;
}

.page-heading {
  min-width: 0;
}

.eyebrow {
  display: block;
  margin-bottom: 8px;
  color: var(--brand);
  font-size: 11px;
  font-weight: 720;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.page-heading h1 {
  margin: 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: var(--font-page-title);
  font-weight: 740;
  letter-spacing: -0.035em;
  line-height: 1.12;
}

.page-heading p {
  max-width: 620px;
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.65;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.service-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 154px;
  padding: 8px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 11px;
  background: var(--surface-raised);
  box-shadow: var(--shadow-xs);
}

.service-summary > span:last-child {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.service-summary strong {
  color: var(--text-strong);
  font-size: 12px;
  font-weight: 650;
}

.service-summary small {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-dot {
  flex: 0 0 9px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--danger);
}

.status-dot.is-online {
  background: var(--success);
}

.status-dot.is-pending {
  background: var(--warning);
  animation: pulse 1.15s ease-in-out infinite;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(330px, 0.75fr);
  grid-template-areas:
    "service appearance"
    "gpu gpu";
  gap: 18px;
}

.settings-panel {
  min-width: 0;
  padding: clamp(20px, 2.3vw, 28px);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.service-panel {
  grid-area: service;
}

.appearance-panel {
  grid-area: appearance;
}

.gpu-panel {
  grid-area: gpu;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}

.panel-title {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 13px;
}

.panel-title > span:last-child {
  min-width: 0;
}

.panel-title h2 {
  margin: 1px 0 0;
  color: var(--text-strong);
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 690;
  letter-spacing: -0.012em;
}

.panel-title p {
  margin: 5px 0 0;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 1.5;
}

.panel-icon {
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 11px;
}

.panel-icon svg {
  width: 18px;
  height: 18px;
}

.service-icon {
  background: var(--brand-soft);
  color: var(--brand);
}

.appearance-icon {
  background: var(--warning-soft);
  color: var(--warning);
}

.gpu-icon {
  background: var(--info-soft);
  color: var(--info);
}

.status-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  padding: 3px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--danger-soft);
  color: var(--danger);
  font-size: 12px;
  font-weight: 650;
}

.status-badge.online {
  background: var(--success-soft);
  color: var(--success);
}

.status-badge.pending {
  background: var(--warning-soft);
  color: var(--warning);
}

.status-badge .el-icon {
  font-size: 13px;
}

.inline-message {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 20px;
  padding: 12px 14px;
  border: 0;
  border-radius: var(--radius-md);
}

.inline-message > svg {
  flex: 0 0 16px;
  width: 16px;
  height: 16px;
  margin-top: 1px;
}

.inline-message strong {
  color: inherit;
  font-size: 12px;
  font-weight: 680;
}

.inline-message p {
  margin: 3px 0 0;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.inline-message.error {
  background: var(--danger-soft);
  color: var(--danger);
}

.inline-message.warning {
  background: var(--warning-soft);
  color: var(--warning);
}

.service-facts {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  margin: 24px 0 0;
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--border-subtle);
}

.fact {
  min-width: 0;
  min-height: 76px;
  display: grid;
  align-content: center;
  gap: 7px;
  padding: 13px 15px;
  background: var(--surface-sunken);
}

.fact dt {
  color: var(--text-muted);
  font-size: 10px;
  font-weight: 620;
  letter-spacing: 0.035em;
  text-transform: uppercase;
}

.fact dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 620;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fact code {
  color: var(--brand-strong);
  font-size: 11px;
  font-weight: 570;
}

.mode-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 3px 8px;
  border: 0;
  border-radius: 6px;
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 620;
}

.mode-chip.development {
  background: var(--warning-soft);
  color: var(--warning);
}

.gpu-header-status {
  display: flex;
  align-items: center;
  gap: 10px;
}

.gpu-header-status > span {
  display: flex;
  align-items: center;
  gap: 5px;
  color: var(--text-muted);
  font-size: 11px;
}

.gpu-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr));
  gap: 12px;
  margin: 24px 0 0;
  padding: 0;
  list-style: none;
}

.gpu-card {
  min-width: 0;
  padding: 17px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.gpu-card-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.gpu-index {
  display: block;
  margin-bottom: 5px;
  color: var(--info);
  font-size: 9px;
  font-weight: 740;
  letter-spacing: 0.09em;
  text-transform: uppercase;
}

.gpu-card h3 {
  margin: 0;
  color: var(--text-strong);
  font-size: 13px;
  font-weight: 660;
  line-height: 1.4;
}

.usage-value {
  flex: 0 0 auto;
  color: var(--brand);
  font-family: var(--font-mono);
  font-size: 17px;
  font-weight: 700;
  letter-spacing: -0.04em;
}

.gpu-card.is-warning .usage-value {
  color: var(--warning);
}

.gpu-card.is-critical .usage-value {
  color: var(--danger);
}

.memory-meter {
  height: 7px;
  margin-top: 17px;
  overflow: hidden;
  border-radius: 999px;
  background: color-mix(in srgb, var(--border-strong) 45%, transparent);
}

.memory-meter span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--brand);
  transition: width 300ms ease;
}

.is-warning .memory-meter span {
  background: var(--warning);
}

.is-critical .memory-meter span {
  background: var(--danger);
}

.memory-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 7px 18px;
  margin-top: 13px;
  color: var(--text-muted);
  font-size: 10px;
}

.memory-legend strong {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  font-weight: 600;
}

.gpu-loading,
.empty-state {
  min-height: 190px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 22px;
  border: 0;
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.gpu-loading strong,
.empty-state strong {
  color: var(--text-strong);
  font-size: 13px;
}

.gpu-loading p,
.empty-state p {
  margin: 5px 0 0;
  color: var(--text-muted);
  font-size: 11px;
}

.loading-orbit,
.empty-icon {
  flex: 0 0 44px;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--info-soft);
  color: var(--info);
}

.loading-orbit svg,
.empty-icon svg {
  width: 19px;
  height: 19px;
}

.loading-orbit {
  animation: pulse 1.2s ease-in-out infinite;
}

.empty-state {
  flex-direction: column;
  gap: 7px;
  padding: 28px;
  text-align: center;
}

.empty-state p {
  max-width: 430px;
  margin-bottom: 8px;
  line-height: 1.5;
}

.spin {
  animation: spin 0.9s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes pulse {
  50% {
    opacity: 0.52;
    transform: scale(0.88);
  }
}

@media (max-width: 1040px) {
  .settings-grid {
    grid-template-columns: 1fr;
    grid-template-areas:
      "service"
      "appearance"
      "gpu";
  }

  .appearance-panel {
    max-width: none;
  }

}

@media (max-width: 720px) {
  .settings-page {
    padding: 28px 16px 42px;
  }

  .page-header {
    align-items: flex-start;
    flex-direction: column;
    gap: 18px;
  }

  .header-actions {
    width: 100%;
  }

  .service-summary {
    flex: 1;
  }

  .settings-panel {
    padding: 19px;
    border-radius: var(--radius-md);
  }

  .service-facts {
    grid-template-columns: 1fr;
  }

  .fact {
    min-height: 68px;
  }

  .gpu-header-status > span {
    display: none;
  }
}

@media (max-width: 480px) {
  .header-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .panel-header {
    gap: 12px;
  }

  .panel-title {
    gap: 10px;
  }

  .panel-icon {
    flex-basis: 34px;
    width: 34px;
    height: 34px;
  }

  .status-badge {
    padding-inline: 7px;
  }

  .gpu-card {
    padding: 15px;
  }

  .memory-legend {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (prefers-reduced-motion: reduce) {
  .status-dot.is-pending,
  .loading-orbit,
  .spin {
    animation: none;
  }

  .memory-meter span {
    transition: none;
  }
}

.eyebrow,
.service-summary small,
.fact dt,
.gpu-index,
.memory-legend {
  font-size: 12px;
}

.service-summary strong,
.panel-title p,
.inline-message p,
.fact code,
.gpu-header-status > span,
.empty-state p {
  font-size: 13px;
}

.inline-message strong,
.fact dd,
.gpu-card h3,
.empty-state strong {
  font-size: 14px;
}

.panel-title h2 {
  font-size: 18px;
}

/* ChatGPT-style settings workspace */
.settings-page {
  width: min(100% - 32px, 1040px);
  min-height: 0;
  margin: 32px auto;
  padding: 0;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.page-header {
  min-height: 62px;
  align-items: center;
  margin: 0;
  padding: 14px 18px 14px 224px;
  border-bottom: 0;
}

.page-heading h1 {
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0;
}

.service-summary {
  min-width: 0;
  padding: 5px 8px;
  border: 0;
  background: transparent;
  box-shadow: none;
}

.service-summary small,
.page-heading p {
  display: none;
}

.settings-workspace {
  min-height: min(680px, calc(100dvh - 128px));
  display: grid;
  grid-template-columns: 224px minmax(0, 1fr);
}

.settings-nav {
  display: grid;
  align-content: start;
  gap: 2px;
  padding: 12px 10px;
  border-right: 0;
  background: var(--surface-nav);
}

.settings-nav button {
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 14px;
  text-align: left;
  cursor: pointer;
}

.settings-nav button:hover,
.settings-nav button.active {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.settings-nav svg {
  width: 17px;
  height: 17px;
}

.settings-content {
  min-width: 0;
  padding: 0 16px 20px;
}

.settings-panel {
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.settings-section-title {
  padding: 18px 0 12px;
  border-bottom: 1px solid var(--border-subtle);
}

.settings-section-title h2 {
  margin: 0;
  color: var(--text-strong);
  font-size: 16px;
  font-weight: 600;
}

.setting-row {
  min-height: 62px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-row > span:first-child {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.setting-row strong {
  color: var(--text-strong);
  font-size: 14px;
  font-weight: 520;
}

.setting-row small {
  color: var(--text-muted);
  font-size: 12px;
}

.theme-segment {
  display: flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--surface-sunken);
}

.theme-segment button {
  min-height: 30px;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 9px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.theme-segment button.active {
  background: var(--surface);
  color: var(--text-strong);
  box-shadow: 0 1px 3px rgb(0 0 0 / 10%);
}

.theme-segment svg {
  width: 14px;
  height: 14px;
}

.service-panel,
.gpu-panel {
  padding: 20px 4px;
}

.service-panel .panel-header,
.gpu-panel .panel-header {
  padding-bottom: 18px;
  border-bottom: 1px solid var(--border-subtle);
}

.service-facts {
  gap: 8px;
  border: 0;
  background: transparent;
}

.fact,
.gpu-card {
  border: 0;
  border-radius: 8px;
  background: var(--surface-sunken);
}

@media (max-width: 720px) {
  .settings-page {
    width: calc(100% - 20px);
    margin: 10px auto;
  }

  .page-header {
    min-height: 56px;
    padding: 10px 12px;
  }

  .header-actions .service-summary {
    display: none;
  }

  .settings-workspace {
    min-height: calc(100dvh - 150px);
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
    align-content: start;
  }

  .settings-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
    align-content: initial;
    align-self: start;
    padding: 8px;
    border-right: 0;
    border-bottom: 1px solid var(--border-subtle);
  }

  .settings-nav button {
    justify-content: center;
    padding-inline: 6px;
  }

  .settings-content {
    padding-inline: 14px;
  }

  .setting-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 8px;
  }

  .settings-page.is-modal {
    width: 100%;
    margin: 0;
  }

  .settings-page.is-modal .settings-workspace {
    min-height: min(680px, 76dvh);
  }
}
</style>
