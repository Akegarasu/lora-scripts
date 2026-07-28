import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router"
const HomePage = () => import("./pages/HomePage.vue")
const IntegrationPage = () => import("./pages/IntegrationPage.vue")
const NotFoundPage = () => import("./pages/NotFoundPage.vue")
const TasksPage = () => import("./pages/TasksPage.vue")
const SettingsPage = () => import("./pages/SettingsPage.vue")
const ToolsPage = () => import("./pages/ToolsPage.vue")
const TaggerPage = () => import("./pages/TaggerPage.vue")
const DatasetEditorPage = () => import("./pages/DatasetEditorPage.vue")
const AnimaFastPage = () => import("./pages/AnimaFastPage.vue")
const TrainingPage = () => import("./pages/TrainingPage.vue")
const TrainingIndexPage = () => import("./pages/TrainingIndexPage.vue")
const GuidePage = () => import("./pages/GuidePage.vue")
const ParamsPage = () => import("./pages/ParamsPage.vue")
const AboutPage = () => import("./pages/AboutPage.vue")
const ChangelogPage = () => import("./pages/ChangelogPage.vue")

const trainingRoutes = [
  ["/lora/basic.html", "LoRA 训练 新手模式", "新手模式", "lora-basic"],
  ["/lora/master.html", "Stable Diffusion LoRA", "专家模式", "lora-master"],
  ["/lora/flux.html", "Flux LoRA 训练", "Flux LoRA", "flux-lora"],
  ["/lora/sd3.html", "Anima LoRA 训练 专家模式", "Anima LoRA", "sd3-lora"],
  ["/lora/anima-fast.html", "Anima LoRA Fast", "Anima Fast", "anima-lora-fast"],
  ["/lora/anima-finetune.html", "Anima Finetune", "全量微调", "anima-finetune"],
  ["/dreambooth/index.html", "Dreambooth 训练 专家模式", "Dreambooth", "dreambooth"],
] as const

const routes: RouteRecordRaw[] = [
  { path: "/", component: HomePage, meta: { title: "Next Trainer" } },
  {
    path: "/lora/index.html",
    component: TrainingIndexPage,
    meta: { title: "LoRA 训练" },
  },
  ...trainingRoutes.map(([path, title, area, schemaName]) => ({
    path,
    component: path === "/lora/anima-fast.html" ? AnimaFastPage : TrainingPage,
    props: { title, area, schemaName },
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
    component: DatasetEditorPage,
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
  { path: "/lora/params.html", component: ParamsPage, meta: { title: "训练参数调节" } },
  { path: "/other/about.html", component: AboutPage, meta: { title: "关于 Next Trainer" } },
  { path: "/other/changelog.html", component: ChangelogPage, meta: { title: "更新日志" } },
  { path: "/help/guide.html", component: GuidePage, meta: { title: "新手上路" } },
  { path: "/lora/sdxl.html", redirect: "/lora/master.html" },
  { path: "/lora/anima-fast", redirect: "/lora/anima-fast.html" },
  { path: "/:pathMatch(.*)*", component: NotFoundPage, meta: { title: "页面不存在" } },
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
