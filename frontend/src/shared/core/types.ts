/** 与后端 GET /api/platform/modules 的响应保持一致。 */

export interface MenuInfo {
  title: string
  path: string
  icon: string
  order: number
  parent: string | null
  permission: string | null
}

export interface ModuleInfo {
  name: string
  title: string
  version: string
  menus: MenuInfo[]
}

export interface PlatformProfile {
  modules: ModuleInfo[]
  permissions: string[]
  superuser: boolean
}
