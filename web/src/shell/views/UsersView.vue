<script setup lang="ts">
import { usePlatformStore, type ApiError } from '@shared/core'
import { computed, onMounted, ref } from 'vue'

import { listRoles, listUsers, setUserActive, setUserRoles, type ManagedRole, type ManagedUser } from '../api/platform'

const platform = usePlatformStore()
const canManage = computed(() => platform.has('platform:user:manage'))
const users = ref<ManagedUser[]>([])
const roles = ref<ManagedRole[]>([])
const error = ref('')
const rolesNotice = ref('')
const savingRoles = ref(false)

async function refresh(): Promise<void> {
  const [usersResult, rolesResult] = await Promise.allSettled([listUsers(), listRoles()])
  if (usersResult.status === 'fulfilled') {
    users.value = usersResult.value
    error.value = ''
  } else {
    error.value = (usersResult.reason as Error).message
  }
  if (rolesResult.status === 'fulfilled') {
    roles.value = rolesResult.value
    rolesNotice.value = ''
  } else {
    roles.value = []
    const reason = rolesResult.reason as ApiError
    rolesNotice.value =
      reason.status === 403 ? '无权查看角色列表，无法分配角色' : `角色列表加载失败，无法分配角色：${reason.message}`
  }
}

async function toggleRole(user: ManagedUser, roleId: number): Promise<void> {
  const previous = user.role_ids
  const next = previous.includes(roleId) ? previous.filter((id) => id !== roleId) : [...previous, roleId]
  user.role_ids = next
  savingRoles.value = true
  try {
    await setUserRoles(user.id, next)
    error.value = ''
  } catch (e) {
    user.role_ids = [...previous]
    error.value = (e as Error).message
  } finally {
    savingRoles.value = false
  }
}

async function toggleActive(user: ManagedUser): Promise<void> {
  try {
    await setUserActive(user.id, !user.is_active)
    user.is_active = !user.is_active
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page-container">
    <div class="page-header">
      <div class="header-titles">
        <div class="breadcrumb">
          <RouterLink to="/" class="breadcrumb-item">应用广场</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">用户管理</span>
        </div>
        <div class="title-with-badge">
          <h1>系统用户管理</h1>
          <span class="header-count-badge">已授权 {{ users.length }} 人</span>
        </div>
        <p class="header-desc">
          查看团队成员登录身份，分配业务与平台模块操作角色，管控账号激活与停用状态。
        </p>
      </div>

      <div class="header-actions">
        <button type="button" class="btn-refresh" @click="refresh">
          <svg viewBox="0 0 20 20" fill="currentColor" class="refresh-icon">
            <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
          </svg>
          <span>刷新数据</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="banner-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <div v-if="rolesNotice" class="warning-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="banner-icon">
        <path fill-rule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1 0 100-2 1 1 0 000 2z" clip-rule="evenodd" />
      </svg>
      <span>{{ rolesNotice }}</span>
    </div>

    <!-- 表格卡片 -->
    <div class="table-card">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>成员信息</th>
              <th>工作邮箱</th>
              <th>授权角色</th>
              <th>账号状态</th>
              <th>最近一次登录</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="user in users" :key="user.id">
              <td>
                <div class="user-cell">
                  <div class="avatar-box">
                    <img v-if="user.avatar_url" :src="user.avatar_url" alt="" class="avatar-img" />
                    <span v-else class="avatar-fallback">
                      {{ (user.display_name || user.username).charAt(0).toUpperCase() }}
                    </span>
                  </div>
                  <div class="user-names">
                    <span class="user-display">{{ user.display_name || user.username }}</span>
                    <span class="user-uname">@{{ user.username }}</span>
                  </div>
                  <span v-if="user.superuser" class="superuser-badge">超级管理员</span>
                </div>
              </td>
              <td class="font-mono text-muted">{{ user.email || '—' }}</td>
              <td>
                <div class="roles-wrap">
                  <label
                    v-for="role in roles"
                    :key="role.id"
                    class="role-checkbox-label"
                    :class="{ 'role-checked': user.role_ids.includes(role.id) }"
                  >
                    <input
                      type="checkbox"
                      :checked="user.role_ids.includes(role.id)"
                      :disabled="!canManage || savingRoles"
                      @change="toggleRole(user, role.id)"
                    />
                    <span>{{ role.name }}</span>
                  </label>
                  <span v-if="roles.length === 0 && !rolesNotice" class="text-weak text-sm">
                    暂无可分配角色（请先在角色管理中创建）
                  </span>
                </div>
              </td>
              <td>
                <div class="status-cell">
                  <span
                    class="status-pill"
                    :class="user.is_active ? 'pill-active' : 'pill-disabled'"
                  >
                    <span class="status-dot"></span>
                    <span>{{ user.is_active ? '正常使用' : '已停用' }}</span>
                  </span>
                  <button
                    v-if="canManage"
                    type="button"
                    class="btn-toggle-active"
                    :class="{ 'btn-warn': user.is_active }"
                    @click="toggleActive(user)"
                  >
                    {{ user.is_active ? '停用' : '启用' }}
                  </button>
                </div>
              </td>
              <td class="text-weak text-sm">{{ user.last_login_at || '尚未登录' }}</td>
            </tr>
            <tr v-if="users.length === 0 && !error">
              <td colspan="5" class="table-empty">暂无注册用户</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

/* 页头 */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: 24px 28px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.breadcrumb-item {
  color: var(--color-text-weak);
  transition: color var(--transition-fast);
}

.breadcrumb-item:hover {
  color: var(--color-primary);
}

.breadcrumb-separator {
  color: var(--color-border-hover);
}

.breadcrumb-current {
  color: var(--color-text-muted);
  font-weight: 500;
}

.title-with-badge {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-with-badge h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.header-count-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-primary-light);
  color: var(--color-primary);
  border: 1px solid var(--color-primary-border);
}

.header-desc {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  max-width: 680px;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  align-items: center;
}

.btn-refresh {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-refresh:hover {
  background: var(--color-surface-subtle);
  color: var(--color-text);
  border-color: var(--color-border-hover);
}

.refresh-icon {
  width: 14px;
  height: 14px;
}

/* 提示条 */
.error-banner,
.warning-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 13px;
}

.error-banner {
  background: var(--color-danger-light);
  border: 1px solid #fecaca;
  color: var(--color-danger-text);
}

.warning-banner {
  background: var(--color-warning-light);
  border: 1px solid #fde68a;
  color: var(--color-warning-text);
}

.banner-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* 表格卡片 */
.table-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.table-scroll {
  overflow-x: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.data-table thead th {
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
}

.data-table tbody td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  vertical-align: middle;
}

.data-table tbody tr:hover td {
  background: #fbfcfe;
}

/* 用户单元格 */
.user-cell {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar-box {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--color-primary-light);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-fallback {
  font-size: 12px;
  font-weight: 700;
  color: var(--color-primary);
}

.user-names {
  display: flex;
  flex-direction: column;
}

.user-display {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.user-uname {
  font-size: 11px;
  color: var(--color-text-weak);
}

.superuser-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: #fef3c7;
  color: #b45309;
  border: 1px solid #fde68a;
}

.roles-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.role-checkbox-label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 3px 8px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.role-checkbox-label:hover {
  border-color: var(--color-border-hover);
}

.role-checked {
  background: var(--color-primary-light);
  border-color: var(--color-primary-border);
  color: var(--color-primary);
  font-weight: 500;
}

.status-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.pill-active {
  background: var(--color-success-light);
  color: var(--color-success-text);
  border: 1px solid #a7f3d0;
}

.pill-active .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}

.pill-disabled {
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
  border: 1px solid var(--color-border);
}

.pill-disabled .status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-weak);
}

.btn-toggle-active {
  padding: 3px 8px;
  font-size: 11px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-toggle-active:hover {
  background: var(--color-surface-subtle);
  color: var(--color-text);
}

.btn-toggle-active.btn-warn:hover {
  background: var(--color-danger-light);
  color: var(--color-danger);
  border-color: #fecaca;
}

.table-empty {
  text-align: center;
  color: var(--color-text-weak);
  padding: 32px 16px !important;
}

.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.text-muted {
  color: var(--color-text-muted);
}

.text-weak {
  color: var(--color-text-weak);
}

.text-sm {
  font-size: 12px;
}
</style>
