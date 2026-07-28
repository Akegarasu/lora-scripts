import { createApp } from "vue"
import { createPinia } from "pinia"
import ElementPlus from "element-plus"
import "element-plus/dist/index.css"
import App from "./App.vue"
import router from "./router"
import "./styles/main.css"
import "./styles/features.css"
import "./styles/anima-fast.css"
import "./styles/training-index.css"
import "./styles/content-pages.css"

createApp(App).use(createPinia()).use(router).use(ElementPlus).mount("#app")
