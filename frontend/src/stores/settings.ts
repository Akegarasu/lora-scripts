import { defineStore } from 'pinia'

import { apiClient } from '@/api/client'
import type { HealthResponse } from '@/api/types'

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
  },
})
