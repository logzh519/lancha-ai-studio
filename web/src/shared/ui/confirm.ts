import { createVNode, defineComponent, h, ref, render } from 'vue'

import ConfirmDialog, { type ConfirmType } from './ConfirmDialog.vue'

export interface ConfirmOptions {
  title?: string
  message?: string
  type?: ConfirmType
  confirmText?: string
  cancelText?: string
  showCancel?: boolean
  showClose?: boolean
  closeOnClickOverlay?: boolean
  closeOnEsc?: boolean
}

/**
 * 通用二次确认对话框函数式调用
 * @example
 * const ok = await confirmDialog({
 *   title: '确认删除',
 *   message: '确定删除该项吗？操作不可恢复。',
 *   type: 'danger',
 *   confirmText: '确认删除',
 * })
 * if (!ok) return
 */
export function confirmDialog(options: ConfirmOptions = {}): Promise<boolean> {
  if (typeof document === 'undefined') {
    return Promise.resolve(false)
  }

  return new Promise((resolve) => {
    const container = document.createElement('div')
    document.body.appendChild(container)

    let isResolved = false
    const finish = (result: boolean) => {
      if (isResolved) return
      isResolved = true
      resolve(result)
    }

    const Wrapper = defineComponent({
      name: 'ConfirmDialogWrapper',
      setup() {
        const open = ref(true)

        return () =>
          h(ConfirmDialog, {
            ...options,
            open: open.value,
            'onUpdate:open': (val: boolean) => {
              open.value = val
            },
            onConfirm: () => {
              open.value = false
              finish(true)
            },
            onCancel: () => {
              open.value = false
              finish(false)
            },
            onAfterLeave: () => {
              render(null, container)
              container.remove()
            },
          })
      },
    })

    const vnode = createVNode(Wrapper)
    render(vnode, container)
  })
}
