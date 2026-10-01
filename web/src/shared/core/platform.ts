/** 平台状态：已启用的模块、当前用户的菜单与权限码。

菜单和权限只有后端一个来源，前端不维护第二份清单。 */

import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { request } from './request'
import type { MenuInfo, ModuleInfo, PlatformProfile } from './types'

export interface MenuNode extends MenuInfo {
  module: string
  children: MenuNode[]
}

export const usePlatformStore = defineStore('platform', () => {
  const modules = ref<ModuleInfo[]>([])
  const permissions = ref(new Set<string>())
  const superuser = ref(false)
  const loaded = ref(false)
  const platformMenus = ref<MenuInfo[]>([])

  async function load(): Promise<void> {
    if (loaded.value) return
    const profile = await request<PlatformProfile>('/platform/modules')
    modules.value = profile.modules
    platformMenus.value = profile.platform_menus
    permissions.value = new Set(profile.permissions)
    superuser.value = profile.superuser
    loaded.value = true
  }

  function has(code: string): boolean {
    return superuser.value || permissions.value.has(code)
  }

  /** 把各模块的菜单合成一棵树：一级按模块分组，模块内部按 parent 嵌套。 */
  const menuTree = computed<MenuNode[]>(() =>
    modules.value
      .filter((module) => module.menus.length > 0)
      .map((module) => {
        const nodes = new Map<string, MenuNode>(
          module.menus.map((menu) => [menu.path, { ...menu, module: module.name, children: [] }]),
        )
        const roots: MenuNode[] = []
        for (const node of nodes.values()) {
          const parent = node.parent ? nodes.get(node.parent) : undefined
          ;(parent ? parent.children : roots).push(node)
        }
        return {
          title: module.title,
          path: `/${module.name}`,
          icon: '',
          order: 0,
          parent: null,
          permission: null,
          module: module.name,
          children: roots,
        }
      }),
  )

  return { modules, permissions, superuser, loaded, platformMenus, load, has, menuTree }
})
