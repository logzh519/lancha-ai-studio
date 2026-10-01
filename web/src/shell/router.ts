/** 路由装配与权限守卫。

模块路由写相对路径，这里统一加上 /<模块名> 前缀，保证前端路由和后端菜单 path 天然对齐。 */

import { usePlatformStore, useSessionStore } from '@shared/core'
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
      { path: '/login', name: 'login', component: () => import('./views/LoginView.vue') },
      { path: '/', component: AppLayout, children },
      { path: '/403', name: 'forbidden', component: () => import('./views/ForbiddenView.vue') },
      { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
    ],
  })

  router.beforeEach(async (to) => {
    const session = useSessionStore()
    if (!session.loaded) {
      // 后端没起时不阻塞登录页，其余页面按未登录处理
      await session.load().catch(() => undefined)
    }
    if (to.name === 'login') {
      return session.user ? { path: '/' } : true
    }
    if (!session.user) {
      return { name: 'login', query: { redirect: to.fullPath } }
    }

    const store = usePlatformStore()
    if (!store.loaded) {
      await store.load().catch(() => undefined)
    }
    const code = to.meta.permission as string | undefined
    return code && !store.has(code) ? { name: 'forbidden' } : true
  })

  return router
}
