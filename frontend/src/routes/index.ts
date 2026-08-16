import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/train' },
    {
      path: '/train',
      name: 'train',
      component: () => import('@/features/train/TrainWorkbench.vue'),
      meta: { title: '训练工作台' },
    },
    {
      path: '/caption',
      name: 'caption',
      component: () => import('@/features/caption/CaptionWorkbench.vue'),
      meta: { title: 'Caption 标注工作台' },
    },
    {
      path: '/caption/jobs/:id',
      name: 'caption-job',
      component: () => import('@/features/caption/CaptionWorkbench.vue'),
      meta: { title: 'Caption 任务复核' },
    },
    {
      path: '/tag-editor',
      name: 'tag-editor',
      component: () => import('@/features/tag-editor/TagEditorWorkbench.vue'),
      meta: { title: 'Caption 编辑器' },
    },
    {
      path: '/tools/tagger',
      redirect: '/tag-editor',
    },
    {
      path: '/jobs/:id?',
      name: 'jobs',
      component: () => import('@/features/jobs/JobsView.vue'),
      meta: { title: '任务中心' },
    },
    {
      path: '/outputs',
      name: 'outputs',
      component: () => import('@/features/outputs/OutputsView.vue'),
      meta: { title: '训练产物' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/features/settings/SettingsView.vue'),
      meta: { title: '环境设置' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/train' },
  ],
})

router.afterEach((to) => {
  document.title = `${String(to.meta.title || 'LoRA Studio')} · lora-scripts`
})
