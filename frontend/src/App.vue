<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowRight,
  Close,
  Cpu,
  EditPen,
  FolderOpened,
  Help,
  Moon,
  Picture,
  Setting,
  Sunny,
  Tickets,
} from '@element-plus/icons-vue'

import { useSettingsStore } from '@/stores/settings'

const SettingsView = defineAsyncComponent(() => import('@/features/settings/SettingsView.vue'))

const route = useRoute()
const settings = useSettingsStore()
const appContent = ref<HTMLElement | null>(null)
const accountMenuOpen = ref(false)
const settingsDialogOpen = ref(false)

function closeAccountMenuOnBlur(event: FocusEvent) {
  const current = event.currentTarget as HTMLElement | null
  const next = event.relatedTarget as Node | null
  if (!current?.contains(next)) accountMenuOpen.value = false
}

function openHelp() {
  window.open('https://github.com/Akegarasu/lora-scripts', '_blank', 'noopener,noreferrer')
  accountMenuOpen.value = false
}

function openSettingsDialog() {
  accountMenuOpen.value = false
  settingsDialogOpen.value = true
}

const navItems = [
  { to: '/train', activePrefixes: ['/train'], label: '训练工作台', shortLabel: '训练', icon: Cpu },
  { to: '/caption', activePrefixes: ['/caption'], label: '数据标注', shortLabel: '标注', icon: Picture },
  { to: '/tag-editor', activePrefixes: ['/tag-editor'], label: '人工编辑', shortLabel: '编辑', icon: EditPen },
  { to: '/jobs', activePrefixes: ['/jobs'], label: '任务中心', shortLabel: '任务', icon: Tickets },
  { to: '/outputs', activePrefixes: ['/outputs'], label: '训练产物', shortLabel: '产物', icon: FolderOpened },
]

const serviceOnline = computed(() => !settings.healthError && settings.health?.status === 'ok')
const serviceLabel = computed(() => {
  if (settings.loadingHealth) return '正在连接'
  if (settings.healthError) return '服务连接失败'
  if (serviceOnline.value) return `服务 ${settings.health?.version || '在线'}`
  return '服务未连接'
})

onMounted(() => {
  void settings.loadHealth()
})

watch(
  () => route.fullPath,
  async () => {
    await nextTick()
    appContent.value?.focus({ preventScroll: true })
  },
  { flush: 'post' },
)
</script>

<template>
  <a class="skip-link" href="#app-content">跳到主要内容</a>

  <div class="app-shell">
    <aside class="app-sidebar">
      <router-link class="app-brand" to="/train" aria-label="lora-scripts 首页">
        <span class="brand-mark" aria-hidden="true">
          <span>L</span>
        </span>
        <span class="brand-copy">
          <strong>LoRA Studio</strong>
        </span>
      </router-link>

      <nav
        class="primary-nav"
        aria-label="主要导航"
        :style="{ '--nav-count': navItems.length }"
      >
        <router-link
          v-for="item in navItems"
          :key="item.to"
          class="nav-item"
          :class="{ 'is-active': item.activePrefixes.some((prefix) => route.path.startsWith(prefix)) }"
          :to="item.to"
        >
          <span class="nav-icon" aria-hidden="true">
            <el-icon><component :is="item.icon" /></el-icon>
          </span>
          <span class="nav-copy">
            <strong>{{ item.label }}</strong>
          </span>
          <span class="nav-mobile-label">{{ item.shortLabel }}</span>
        </router-link>
      </nav>

      <div class="sidebar-footer">
        <div class="account-wrap" @focusout="closeAccountMenuOnBlur">
          <button
            class="account-trigger"
            type="button"
            aria-haspopup="menu"
            :aria-expanded="accountMenuOpen"
            @keydown.esc="accountMenuOpen = false"
            @click="accountMenuOpen = !accountMenuOpen"
          >
            <span class="account-avatar" aria-hidden="true">LS</span>
            <span class="account-copy"><strong>LoRA Studio</strong><small>本地工作区</small></span>
            <el-icon class="account-chevron"><ArrowRight /></el-icon>
          </button>
          <div v-if="accountMenuOpen" class="account-menu" role="menu">
            <div class="account-menu-head">
              <span class="account-avatar large" aria-hidden="true">LS</span>
              <span><strong>LoRA Studio</strong><small>{{ serviceLabel }}</small></span>
            </div>
            <div class="account-divider" />
            <button class="account-menu-item" type="button" role="menuitem" @click="openSettingsDialog">
              <el-icon><Setting /></el-icon><span>设置</span>
            </button>
            <button class="account-menu-item" type="button" role="menuitem" @click="settings.toggleTheme">
              <el-icon><Sunny v-if="settings.theme === 'dark'" /><Moon v-else /></el-icon>
              <span>{{ settings.theme === 'dark' ? '浅色外观' : '深色外观' }}</span>
            </button>
            <button class="account-menu-item" type="button" role="menuitem" @click="openHelp">
              <el-icon><Help /></el-icon><span>帮助</span><el-icon class="menu-end"><ArrowRight /></el-icon>
            </button>
          </div>
        </div>
      </div>
    </aside>

    <main id="app-content" ref="appContent" class="app-content" tabindex="-1">
      <router-view />
    </main>

    <el-dialog
      v-model="settingsDialogOpen"
      class="settings-dialog"
      modal-class="settings-dialog-overlay"
      width="min(920px, calc(100vw - 32px))"
      destroy-on-close
      append-to-body
      aria-label="设置"
    >
      <SettingsView modal @close="settingsDialogOpen = false" />
    </el-dialog>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100dvh;
}

.app-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: 50;
  width: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  padding: 12px 8px 8px;
  border-right: 0;
  background: var(--surface-nav);
  box-shadow: var(--shadow-sidebar);
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 3px 10px;
  color: var(--text-strong);
  text-decoration: none;
}

.brand-mark {
  display: none;
}

.brand-mark span {
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 760;
}

.brand-copy {
  min-width: 0;
  display: grid;
}

.brand-copy strong {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 720;
  letter-spacing: 0;
}

.primary-nav {
  display: grid;
  gap: 2px;
  margin-top: 14px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 36px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 12px;
  color: var(--text-secondary);
  text-decoration: none;
  transition:
    color 160ms ease,
    background-color 160ms ease,
    border-color 160ms ease,
    transform 160ms ease;
}

.nav-item:hover {
  border-color: transparent;
  background: var(--surface-hover);
  color: var(--text-strong);
  transform: none;
}

.nav-item.is-active {
  border-color: transparent;
  background: var(--brand-soft);
  color: var(--brand-strong);
}

.nav-icon {
  flex: 0 0 20px;
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  font-size: 16px;
}

.is-active .nav-icon {
  background: transparent;
  box-shadow: none;
}

.nav-copy {
  min-width: 0;
  display: grid;
  gap: 0;
}

.nav-copy strong {
  font-size: 14px;
  font-weight: 540;
}

.nav-mobile-label {
  display: none;
}

.sidebar-footer {
  display: grid;
  gap: 8px;
  margin-top: auto;
}

.service-pill {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 34px;
  padding: 5px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: 7px;
  background: var(--surface-raised);
  color: var(--text-secondary);
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.service-pill:hover {
  border-color: var(--border-strong);
  color: var(--text-strong);
}

.service-dot {
  flex: 0 0 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--danger);
}

.service-dot.online {
  background: var(--success);
}

.service-dot.pending {
  background: var(--warning);
  animation: service-pulse 1.2s ease-in-out infinite;
}

.account-wrap {
  position: relative;
  margin-top: 4px;
}

.account-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 48px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 14px;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.account-trigger:hover,
.account-trigger:focus-visible {
  border-color: var(--border-subtle);
  background: var(--surface-hover);
}

.account-avatar {
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--text-strong);
  color: var(--surface);
  font-size: 10px;
  font-weight: 760;
}

.account-avatar.large {
  flex-basis: 32px;
  width: 32px;
  height: 32px;
}

.account-copy,
.account-menu-head > span:last-child {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.account-copy strong,
.account-menu-head strong {
  overflow: hidden;
  color: var(--text-strong);
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-copy small,
.account-menu-head small {
  color: var(--text-muted);
  font-size: 10px;
}

.account-chevron {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 14px;
}

.account-menu {
  position: absolute;
  right: -2px;
  bottom: calc(100% + 8px);
  z-index: 80;
  width: 236px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface-overlay);
  box-shadow: 0 14px 34px rgb(0 0 0 / 14%);
}

.account-menu-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 7px 9px;
}

.account-divider {
  height: 1px;
  margin: 2px 6px 6px;
  background: var(--border-subtle);
}

.account-menu-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 34px;
  padding: 6px 8px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: 13px;
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}

.account-menu-item:hover,
.account-menu-item:focus-visible {
  background: var(--surface-hover);
  color: var(--text-strong);
}

.account-menu-item .el-icon {
  color: var(--text-secondary);
  font-size: 16px;
}

.account-menu-item .menu-end {
  margin-left: auto;
}

:global(.settings-dialog-overlay) {
  background-color: rgb(15 15 15 / 38%) !important;
  backdrop-filter: blur(8px);
}

:global(.settings-dialog.el-dialog) {
  --el-dialog-padding-primary: 0;
  overflow: hidden;
  border-radius: 14px;
}

:global(.settings-dialog .el-dialog__header) {
  display: none;
}

:global(.settings-dialog .el-dialog__body) {
  padding: 0;
}

.app-content {
  min-width: 0;
  min-height: 100dvh;
  margin-left: var(--sidebar-width);
  outline: none;
}

@keyframes service-pulse {
  50% {
    opacity: 0.45;
    transform: scale(0.82);
  }
}

@media (max-width: 1080px) {
  .app-sidebar {
    width: var(--sidebar-rail-width);
    align-items: center;
    padding-inline: 10px;
  }

  .app-brand {
    padding-inline: 0;
  }

  .brand-copy,
  .nav-copy,
  .service-pill span:last-child,
  .account-copy,
  .account-chevron {
    display: none;
  }

  .primary-nav {
    width: 100%;
  }

  .nav-item {
    justify-content: center;
    padding-inline: 0;
  }

  .nav-item.is-active::before {
    left: -11px;
  }

  .service-pill,
  .account-trigger {
    width: 42px;
    justify-content: center;
    padding-inline: 0;
  }

  .app-content {
    margin-left: var(--sidebar-rail-width);
  }
}

@media (max-width: 760px) {
  .app-shell {
    padding-bottom: calc(70px + env(safe-area-inset-bottom));
  }

  .app-sidebar {
    inset: auto 0 0;
    width: auto;
    max-width: 100vw;
    height: calc(64px + env(safe-area-inset-bottom));
    display: block;
    overflow: hidden;
    padding: 6px 10px calc(6px + env(safe-area-inset-bottom));
    border-top: 1px solid var(--border-subtle);
    border-right: 0;
  }

  .app-brand,
  .sidebar-footer {
    display: none;
  }

  .primary-nav {
    height: 100%;
    width: 100%;
    display: grid;
    grid-template-columns: repeat(var(--nav-count), minmax(0, 1fr)) !important;
    gap: 6px;
    margin: 0;
  }

  .nav-item {
    min-width: 0;
    overflow: hidden;
    min-height: 52px;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    padding: 4px;
    border-radius: 11px;
  }

  .nav-item:hover {
    transform: none;
  }

  .nav-item.is-active::before {
    inset: auto 25% -7px;
    width: 50%;
    height: 3px;
    border-radius: 999px 999px 0 0;
  }

  .nav-icon {
    width: auto;
    height: 25px;
    flex-basis: 25px;
    background: transparent;
    box-shadow: none;
    font-size: 19px;
  }

  .is-active .nav-icon {
    background: transparent;
    box-shadow: none;
  }

  .nav-mobile-label {
    display: block;
    max-width: 100%;
    overflow: hidden;
    font-size: 11px;
    font-weight: 600;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .app-content {
    margin-left: 0;
  }
}
</style>
