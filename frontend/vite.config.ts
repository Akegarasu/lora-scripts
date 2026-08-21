import { fileURLToPath, URL } from 'node:url'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

const projectRoot = fileURLToPath(new URL('..', import.meta.url))
const releaseInfo = JSON.parse(readFileSync(new URL('../version.json', import.meta.url), 'utf8')) as {
  version: string
  frontend: { version: string }
}

function buildCommit() {
  if (process.env.MIKAZUKI_BUILD_COMMIT) return process.env.MIKAZUKI_BUILD_COMMIT
  if (process.env.GITHUB_SHA) return process.env.GITHUB_SHA
  try {
    return execFileSync('git', ['rev-parse', 'HEAD'], { cwd: projectRoot, encoding: 'utf8' }).trim()
  } catch {
    return ''
  }
}

export default defineConfig({
  plugins: [
    vue(),
    {
      name: 'mikazuki-build-info',
      generateBundle() {
        this.emitFile({
          type: 'asset',
          fileName: 'build-info.json',
          source: JSON.stringify(
            {
              schemaVersion: 1,
              appVersion: releaseInfo.version,
              frontendVersion: releaseInfo.frontend.version,
              commit: buildCommit(),
              builtAt: new Date().toISOString(),
            },
            null,
            2,
          ),
        })
      },
    },
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:28000',
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
