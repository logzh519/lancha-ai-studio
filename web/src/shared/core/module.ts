/** 前端模块契约。

模块只提供路由和页面，不写菜单、不写权限清单——那些由后端 module.py 声明。
路由 path 写相对路径（如 'items'），shell 会自动加上 /<模块名> 前缀，
这样模块名改了不需要改模块内部的代码。 */

import type { RouteRecordRaw } from 'vue-router'

export interface ShellContext {
  /** 判断当前用户是否具备某个权限码，用于页面内按钮级控制。 */
  hasPermission: (code: string) => boolean
}

export interface AppModule {
  name: string
  routes: RouteRecordRaw[]
  /** 可选的初始化钩子，在路由注册后执行一次。 */
  setup?: (ctx: ShellContext) => void | Promise<void>
}

export const defineModule = (module: AppModule): AppModule => module
