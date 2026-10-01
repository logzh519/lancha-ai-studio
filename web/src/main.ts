import { permission, usePlatformStore } from '@shared/core'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './shell/App.vue'
import { loadModules } from './shell/modules'
import { createAppRouter } from './shell/router'
import './shared/ui/styles.css'

async function bootstrap(): Promise<void> {
  const app = createApp(App)
  app.use(createPinia())
  app.directive('permission', permission)

  const modules = loadModules()
  const router = createAppRouter(modules)
  app.use(router)
  await router.isReady()

  const platform = usePlatformStore()
  const context = { hasPermission: (code: string) => platform.has(code) }
  for (const module of modules) {
    await module.setup?.(context)
  }

  app.mount('#app')
}

void bootstrap()
