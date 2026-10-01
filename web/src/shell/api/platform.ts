/** 平台管理接口。shell 自己的能力，不属于任何业务模块。 */

import { request } from '@shared/core'

export interface ManagedUser {
  id: number
  username: string
  display_name: string
  avatar_url: string
  email: string
  superuser: boolean
  is_active: boolean
  last_login_at: string | null
  role_ids: number[]
}

export interface ManagedRole {
  id: number
  code: string
  name: string
  description: string
  permission_ids: number[]
  user_count: number
}

export interface PermissionGroup {
  module: string
  permissions: Array<{ id: number; code: string; name: string }>
}

export const listUsers = () => request<ManagedUser[]>('/platform/users')

export const setUserRoles = (id: number, roleIds: number[]) =>
  request<void>(`/platform/users/${id}/roles`, { method: 'PATCH', body: JSON.stringify({ role_ids: roleIds }) })

export const setUserActive = (id: number, isActive: boolean) =>
  request<void>(`/platform/users/${id}/active`, { method: 'PATCH', body: JSON.stringify({ is_active: isActive }) })

export const listRoles = () => request<ManagedRole[]>('/platform/roles')

export const createRole = (payload: Omit<ManagedRole, 'id' | 'user_count'>) =>
  request<ManagedRole>('/platform/roles', { method: 'POST', body: JSON.stringify(payload) })

export const updateRole = (id: number, payload: Omit<ManagedRole, 'id' | 'code' | 'user_count'>) =>
  request<ManagedRole>(`/platform/roles/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })

export const deleteRole = (id: number) => request<void>(`/platform/roles/${id}`, { method: 'DELETE' })

export const listPermissions = () => request<PermissionGroup[]>('/platform/permissions')
