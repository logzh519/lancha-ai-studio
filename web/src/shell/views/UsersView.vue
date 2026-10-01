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
// 角色保存期间全局禁用复选框：后端是整体替换，并发提交会丢更新
const savingRoles = ref(false)

async function refresh(): Promise<void> {
  // 用户列表是页面核心；角色列表需要另一项权限，失败不能拖垮用户表格，故分开容错
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
  // 乐观更新：先让状态与已被浏览器翻转的 DOM 一致，失败再回滚（换引用以确保触发重渲染）
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
  <section>
    <h1>用户管理</h1>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="rolesNotice" class="muted">{{ rolesNotice }}</p>
    <table>
      <thead>
        <tr>
          <th>用户</th>
          <th>邮箱</th>
          <th>角色</th>
          <th>状态</th>
          <th>最后登录</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in users" :key="user.id">
          <td class="who">
            <img v-if="user.avatar_url" :src="user.avatar_url" alt="" />
            <span>{{ user.display_name || user.username }}</span>
            <em v-if="user.superuser">超级管理员</em>
          </td>
          <td>{{ user.email }}</td>
          <td class="roles">
            <label v-for="role in roles" :key="role.id">
              <input
                type="checkbox"
                :checked="user.role_ids.includes(role.id)"
                :disabled="!canManage || savingRoles"
                @change="toggleRole(user, role.id)"
              />
              {{ role.name }}
            </label>
            <span v-if="roles.length === 0 && !rolesNotice" class="muted">先在角色管理里创建角色</span>
          </td>
          <td>
            <button type="button" :disabled="!canManage" @click="toggleActive(user)">
              {{ user.is_active ? '停用' : '启用' }}
            </button>
            <span v-if="!user.is_active" class="muted">已停用</span>
          </td>
          <td class="muted">{{ user.last_login_at ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
table {
  width: 100%;
  margin-top: var(--space-md);
  border-collapse: collapse;
  background: var(--color-surface);
}

th,
td {
  padding: 10px var(--space-sm);
  border-bottom: 1px solid var(--color-border);
  font-size: 14px;
  text-align: left;
}

th {
  color: var(--color-text-weak);
  font-size: 12px;
  font-weight: 500;
}

.who {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.who img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
}

.who em {
  padding: 1px 6px;
  border-radius: var(--radius);
  background: var(--color-bg);
  color: var(--color-primary);
  font-size: 11px;
  font-style: normal;
}

.roles {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
}

.roles label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.muted {
  color: var(--color-text-weak);
  font-size: 12px;
}

.error {
  color: #d03050;
}
</style>
