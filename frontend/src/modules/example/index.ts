/** 模块注册入口：只声明路由，不写菜单和权限清单（那些在后端 module.py 里）。

路由 path 用相对路径，shell 会自动加上 /example 前缀。
meta.permission 必须是后端已声明的权限码，否则用户会被守卫挡在 403。 */

import { defineModule } from '@shared/core'

export default defineModule({
  name: 'example',
  routes: [
    {
      path: 'items',
      component: () => import('./views/ItemListView.vue'),
      meta: { permission: 'example:item:view' },
    },
  ],
})
