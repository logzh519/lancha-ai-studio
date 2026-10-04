/** TikTok：爆款视频脚本库。 */

import { defineModule } from '@shared/core'

export default defineModule({
  name: 'tiktok',
  routes: [
    {
      path: 'script-templates',
      component: () => import('./views/ScriptTemplateListView.vue'),
      meta: { permission: 'tiktok:script_template:view' },
    },
    {
      path: 'script-templates/new',
      component: () => import('./views/ScriptTemplateFormView.vue'),
      meta: { permission: 'tiktok:script_template:create' },
    },
    {
      path: 'script-templates/:id',
      component: () => import('./views/ScriptTemplateFormView.vue'),
      meta: { permission: 'tiktok:script_template:view' },
    },
  ],
})
