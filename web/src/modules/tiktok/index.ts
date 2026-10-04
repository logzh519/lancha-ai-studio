/** TikTok：账号管理。 */

import { defineModule } from '@shared/core'

export default defineModule({
  name: 'tiktok',
  routes: [
    {
      path: 'accounts',
      component: () => import('./views/AccountListView.vue'),
      meta: { permission: 'tiktok:account:view' },
    },
  ],
})
