/** Example A：创建条目并发布 example_a.item_created 事件。

路由 path 用相对路径，shell 会自动加上 /example_a 前缀。
meta.permission 必须是后端已声明的权限码，否则用户会被守卫挡在 403。 */

import { defineModule } from '@shared/core'

export default defineModule({
  name: 'example_a',
  routes: [
    {
      path: 'items',
      component: () => import('./views/ItemListView.vue'),
      meta: { permission: 'example_a:item:view' },
    },
  ],
})
