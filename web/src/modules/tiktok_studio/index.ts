/** TikTok：爆款视频脚本库、商品资产库。 */

import { defineModule } from '@shared/core'

export default defineModule({
  name: 'tiktok_studio',
  routes: [
    {
      path: 'script-templates',
      component: () => import('./views/ScriptTemplateListView.vue'),
      meta: { permission: 'tiktok_studio:script_template:view' },
    },
    {
      path: 'script-templates/new',
      component: () => import('./views/ScriptTemplateFormView.vue'),
      meta: { permission: 'tiktok_studio:script_template:create' },
    },
    {
      path: 'script-templates/:id',
      component: () => import('./views/ScriptTemplateFormView.vue'),
      meta: { permission: 'tiktok_studio:script_template:view' },
    },
    {
      path: 'product-masters',
      component: () => import('./views/ProductMasterListView.vue'),
      meta: { permission: 'tiktok_studio:product_master:view' },
    },
    {
      path: 'product-masters/new',
      component: () => import('./views/ProductMasterFormView.vue'),
      meta: { permission: 'tiktok_studio:product_master:create' },
    },
    {
      path: 'product-masters/:id',
      component: () => import('./views/ProductMasterFormView.vue'),
      meta: { permission: 'tiktok_studio:product_master:view' },
    },
  ],
})
