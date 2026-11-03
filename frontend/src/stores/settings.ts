import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type { HealthResponse, McpSettingsResponse } from '@/api/types'

type Theme = 'light' | 'dark'

const THEME_KEY = 'ls-theme'

function readStoredTheme(): Theme {
  const stored = localStorage.getItem(THEME_KEY)
  if (stored === 'dark' || stored === 'light') return stored
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}

export const useSettingsStore = defineStore('settings', {
  state: () => ({
    theme: readStoredTheme() as Theme,
    apiBase: '/api/v2',
    health: null as HealthResponse | null,
    healthError: '',
    loadingHealth: false,
    mcp: null as McpSettingsResponse | null,
    mcpError: '',
    loadingMcp: false,
    savingMcp: false,
  }),
  actions: {
    initTheme() {
      applyTheme(this.theme)
    },
    setTheme(theme: Theme) {
      this.theme = theme
      localStorage.setItem(THEME_KEY, theme)
      applyTheme(theme)
    },
    toggleTheme() {
      this.setTheme(this.theme === 'dark' ? 'light' : 'dark')
    },
    async loadHealth() {
      this.loadingHealth = true
      this.healthError = ''
      try {
        this.health = await apiClient.getHealth()
      } catch (error) {
        this.healthError = error instanceof Error ? error.message : String(error)
      } finally {
        this.loadingHealth = false
      }
    },
    async loadMcpSettings() {
      if (this.loadingMcp || this.savingMcp) return
      this.loadingMcp = true
      this.mcpError = ''
      try {
        this.mcp = await apiClient.getMcpSettings()
      } catch (error) {
        this.mcp = null
        this.mcpError = error instanceof Error ? error.message : String(error)
      } finally {
        this.loadingMcp = false
      }
    },
    async setMcpEnabled(enabled: boolean) {
      if (!this.mcp || this.loadingMcp || this.savingMcp) return
      this.savingMcp = true
      this.mcpError = ''
      try {
        this.mcp = await apiClient.setMcpEnabled(enabled)
      } catch (error) {
        // A failed response may follow an accepted update. Read back before
        // allowing another change; never assume that the previous state won.
        const message = error instanceof Error ? error.message : String(error)
        try {
          this.mcp = await apiClient.getMcpSettings()
        } catch {
          this.mcp = null
        }
        this.mcpError = `未能确认设置更新：${message}`
      } finally {
        this.savingMcp = false
      }
    },
  },
})
