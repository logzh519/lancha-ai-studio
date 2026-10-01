/** 当前登录用户。未登录时后端返回 401，store 保持 user=null，由路由守卫跳登录页。 */

import { defineStore } from 'pinia'
import { ref } from 'vue'

import { request, type ApiError } from './request'
import type { SessionUser } from './types'

export const useSessionStore = defineStore('session', () => {
  const user = ref<SessionUser | null>(null)
  const loaded = ref(false)

  async function load(): Promise<void> {
    try {
      user.value = await request<SessionUser>('/platform/auth/me')
    } catch (e) {
      if ((e as ApiError).status !== 401) throw e
      user.value = null
    } finally {
      loaded.value = true
    }
  }

  async function startFeishuLogin(): Promise<void> {
    const { authorize_url } = await request<{ authorize_url: string }>('/platform/auth/feishu/login-url', {
      method: 'POST',
    })
    window.location.href = authorize_url
  }

  async function logout(): Promise<void> {
    await request<void>('/platform/auth/logout', { method: 'POST' })
    user.value = null
    loaded.value = false
    window.location.href = '/login'
  }

  return { user, loaded, load, logout, startFeishuLogin }
})
