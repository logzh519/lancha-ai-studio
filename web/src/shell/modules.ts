/** 扫描业务模块入口，并只动态导入 VITE_ENABLED_MODULES 启用的模块。 */

import type { AppModule } from '@shared/core'

const registry = import.meta.glob<{ default: AppModule }>('../modules/*/index.ts')

export async function loadModules(): Promise<AppModule[]> {
  const enabled = (import.meta.env.VITE_ENABLED_MODULES ?? '')
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean)

  const entries = Object.entries(registry).filter(([path]) => {
    const directory = path.split('/')[2]
    return enabled.length === 0 || enabled.includes(directory)
  })
  const modules = await Promise.all(entries.map(async ([path, load]) => {
    const loaded = await load()
    const directory = path.split('/')[2]
    const module = loaded.default
    if (module.name !== directory) {
      throw new Error(`模块 ${directory} 的 name 为 "${module.name}"，须与目录名一致`)
    }
    return module
  }))
  return modules.sort((a, b) => a.name.localeCompare(b.name))
}
