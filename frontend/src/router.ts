import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
import HomePage from "./pages/HomePage.vue"
import IntegrationPage from "./pages/IntegrationPage.vue"
import MigrationPage from "./pages/MigrationPage.vue"
import TasksPage from "./pages/TasksPage.vue"
import SettingsPage from "./pages/SettingsPage.vue"
import ToolsPage from "./pages/ToolsPage.vue"
import TaggerPage from "./pages/TaggerPage.vue"

const trainingRoutes = [
  ["/lora/basic.html", "LoRA 训练 新手模式", "basic"],
  ["/lora/master.html", "Stable Diffusion LoRA", "master"],
  ["/lora/flux.html", "Flux LoRA 训练", "flux-lora"],
  ["/lora/sd3.html", "Anima LoRA 训练 专家模式", "sd3-lora"],
  ["/lora/anima-fast.html", "Anima LoRA Fast", "anima-lora-fast"],
  ["/lora/anima-finetune.html", "Anima Finetune", "anima-finetune"],
  ["/dreambooth/index.html", "Dreambooth 训练 专家模式", "dreambooth"],
] as const

const routes: RouteRecordRaw[] = [
  { path: "/", component: HomePage, meta: { title: "Next Trainer" } },
  {
    path: "/lora/index.html",
    component: MigrationPage,
    props: { title: "LoRA 训练", area: "训练模式入口" },
    meta: { title: "LoRA 训练" },
  },
  ...trainingRoutes.map(([path, title, area]) => ({
    path,
    component: MigrationPage,
    props: { title, area, training: true },
    meta: { title },
  })),
  {
    path: "/tagger.html",
    component: TaggerPage,
    meta: { title: "Tagger 标注工具" },
  },
  {
    path: "/native-tageditor.html",
    alias: "/dataset-editor.html",
    component: MigrationPage,
    props: { title: "数据集标签编辑器", area: "Caption 与 Tag 编辑" },
    meta: { title: "数据集标签编辑器" },
  },
  {
    path: "/tensorboard.html",
    component: IntegrationPage,
    props: { title: "TensorBoard", src: "/proxy/tensorboard/", configurable: true },
    meta: { title: "TensorBoard" },
  },
  {
    path: "/tageditor.html",
    component: IntegrationPage,
    props: { title: "旧版标签编辑器", src: "/proxy/tageditor/" },
    meta: { title: "旧版标签编辑器" },
  },
  { path: "/task.html", component: TasksPage, meta: { title: "训练任务" } },
  { path: "/lora/tools.html", component: ToolsPage, meta: { title: "LoRA 脚本工具" } },
  { path: "/other/settings.html", component: SettingsPage, meta: { title: "训练 UI 设置" } },
  ...[
    ["/lora/params.html", "训练参数调节", "参数说明"],
    ["/other/about.html", "关于 Next Trainer", "项目信息"],
    ["/other/changelog.html", "更新日志", "版本记录"],
    ["/help/guide.html", "新手上路", "使用指南"],
  ].map(([path, title, area]) => ({
    path,
    component: MigrationPage,
    props: { title, area },
    meta: { title },
  })),
  { path: "/lora/sdxl.html", redirect: "/lora/master.html" },
  { path: "/lora/anima-fast", redirect: "/lora/anima-fast.html" },
  { path: "/:pathMatch(.*)*", component: MigrationPage, props: { title: "页面不存在", area: "404" } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((route) => {
  const title = typeof route.meta.title === "string" ? route.meta.title : "Next Trainer"
  document.title = `${title} | 训练 UI`
})

export default router
