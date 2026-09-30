/** v-permission="'example:item:create'"：没有该权限时把元素从 DOM 移除。 */

import type { Directive } from 'vue'

import { usePlatformStore } from './platform'

export const permission: Directive<HTMLElement, string> = {
  mounted(el, binding) {
    if (!usePlatformStore().has(binding.value)) {
      el.remove()
    }
  },
}
