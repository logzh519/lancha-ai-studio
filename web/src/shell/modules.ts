/** 模块装载：构建时扫描 src/modules 下每个模块的 index.ts，按 VITE_ENABLED_MODULES 过滤。

没有启用的模块不会打进产物；即使打进了，菜单也只按后端返回的数据渲染。 */

import type { AppModule } from '@shared/core'

const registry = import.meta.glob<{ default: AppModule }>('../modules/*/index.ts', { eager: true })

export function loadModules(): AppModule[] {
  const enabled = (import.meta.env.VITE_ENABLED_MODULES ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean)

  const modules: AppModule[] = []
  for (const [path, loaded] of Object.entries(registry)) {
    const directory = path.split('/')[2]
    const module = loaded.default
    if (module.name !== directory) {
      throw new Error(`模块 ${directory} 的 name 为 "${module.name}"，须与目录名一致`)
    }
    if (enabled.length === 0 || enabled.includes(directory)) {
      modules.push(module)
    }
  }
  return modules.sort((a, b) => a.name.localeCompare(b.name))
}
