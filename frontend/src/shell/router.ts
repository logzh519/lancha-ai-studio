/** 路由装配与权限守卫。

模块路由写相对路径，这里统一加上 /<模块名> 前缀，保证前端路由和后端菜单 path 天然对齐。 */

import { usePlatformStore } from '@shared/core'
import type { AppModule } from '@shared/core'
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import AppLayout from './layout/AppLayout.vue'

function prefixRoutes(module: AppModule): RouteRecordRaw[] {
  return module.routes.map(
    (route) =>
      ({
        ...route,
        path: `${module.name}/${route.path}`.replace(/\/$/, ''),
        name: route.name ? `${module.name}/${String(route.name)}` : undefined,
      }) as RouteRecordRaw,
  )
}

export function createAppRouter(modules: AppModule[]) {
  const children: RouteRecordRaw[] = [
    { path: '', name: 'home', component: () => import('./views/HomeView.vue') },
    ...modules.flatMap(prefixRoutes),
  ]

  const router = createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/', component: AppLayout, children },
      { path: '/403', name: 'forbidden', component: () => import('./views/ForbiddenView.vue') },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
    ],
  })

  router.beforeEach(async (to) => {
    const store = usePlatformStore()
    if (!store.loaded) {
      // 后端没起时不阻塞页面，菜单为空，具体接口各自报错
      await store.load().catch(() => undefined)
    }
    const code = to.meta.permission as string | undefined
    return code && !store.has(code) ? { name: 'forbidden' } : true
  })

  return router
}
