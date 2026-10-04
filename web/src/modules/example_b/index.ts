import { defineModule } from '@shared/core'

export default defineModule({
  name: 'example_b',
  routes: [
    {
      path: 'events',
      component: () => import('./views/EventInboxView.vue'),
      meta: { permission: 'example_b:event:view' },
    },
  ],
})