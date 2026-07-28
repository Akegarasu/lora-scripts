import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:28000",
      "/proxy": "http://127.0.0.1:28000",
      "/train-log": "http://127.0.0.1:28000",
      "/font-roboto": "http://127.0.0.1:28000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
})
