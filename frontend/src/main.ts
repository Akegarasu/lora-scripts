import {
  ElAlert,
  ElButton,
  ElCheckbox,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElOption,
  ElOptionGroup,
  ElPagination,
  ElProgress,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSkeleton,
  ElSkeletonItem,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTooltip,
  provideGlobalConfig,
} from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './routes'
import { useSettingsStore } from './stores/settings'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'vue-virtual-scroller/index.css'
import './styles.css'

const pinia = createPinia()
const app = createApp(App).use(pinia).use(router)

const elementComponents = [
  ElAlert,
  ElButton,
  ElCheckbox,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElOption,
  ElOptionGroup,
  ElPagination,
  ElProgress,
  ElRadioButton,
  ElRadioGroup,
  ElSelect,
  ElSkeleton,
  ElSkeletonItem,
  ElSwitch,
  ElTabPane,
  ElTable,
  ElTableColumn,
  ElTabs,
  ElTag,
  ElTooltip,
]

for (const component of elementComponents) {
  if (component.name) app.component(component.name, component)
}
app.use(ElLoading)
provideGlobalConfig({ locale: zhCn }, app, true)

useSettingsStore(pinia).initTheme()

app.mount('#app')
