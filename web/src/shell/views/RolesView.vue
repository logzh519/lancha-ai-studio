<script setup lang="ts">
import { usePlatformStore } from '@shared/core'
import { computed, onMounted, ref } from 'vue'

import {
  createRole,
  deleteRole,
  listPermissions,
  listRoles,
  updateRole,
  type ManagedRole,
  type PermissionGroup,
} from '../api/platform'

const platform = usePlatformStore()
const canManage = computed(() => platform.has('platform:role:manage'))
const roles = ref<ManagedRole[]>([])
const groups = ref<PermissionGroup[]>([])
const editing = ref<ManagedRole | null>(null)
const draft = ref({ code: '', name: '', description: '', permission_ids: [] as number[] })
const error = ref('')

async function refresh(): Promise<void> {
  try {
    ;[roles.value, groups.value] = await Promise.all([listRoles(), listPermissions()])
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

function startCreate(): void {
  editing.value = null
  draft.value = { code: '', name: '', description: '', permission_ids: [] }
}

function startEdit(role: ManagedRole): void {
  editing.value = role
  draft.value = {
    code: role.code,
    name: role.name,
    description: role.description,
    permission_ids: [...role.permission_ids],
  }
}

function togglePermission(id: number): void {
  const current = draft.value.permission_ids
  draft.value.permission_ids = current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
}

async function submit(): Promise<void> {
  try {
    if (editing.value) {
      await updateRole(editing.value.id, {
        name: draft.value.name,
        description: draft.value.description,
        permission_ids: draft.value.permission_ids,
      })
    } else {
      await createRole(draft.value)
    }
    startCreate()
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function remove(role: ManagedRole): Promise<void> {
  try {
    await deleteRole(role.id)
    if (editing.value?.id === role.id) startCreate()
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <h1>角色管理</h1>
    <p v-if="error" class="error">{{ error }}</p>

    <table>
      <thead>
        <tr>
          <th>角色</th>
          <th>标识</th>
          <th>权限数</th>
          <th>用户数</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="role in roles" :key="role.id">
          <td>{{ role.name }}</td>
          <td class="muted">{{ role.code }}</td>
          <td>{{ role.permission_ids.length }}</td>
          <td>{{ role.user_count }}</td>
          <td>
            <button type="button" :disabled="!canManage" @click="startEdit(role)">编辑</button>
            <button type="button" :disabled="!canManage" @click="remove(role)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <form v-if="canManage" @submit.prevent="submit">
      <h2>{{ editing ? `编辑角色：${editing.name}` : '新建角色' }}</h2>
      <div class="fields">
        <input v-model="draft.code" :disabled="!!editing" placeholder="标识，如 ops" required />
        <input v-model="draft.name" placeholder="名称，如 运营" required />
        <input v-model="draft.description" placeholder="说明（可选）" />
      </div>
      <div v-for="group in groups" :key="group.module" class="group">
        <h3>{{ group.module }}</h3>
        <label v-for="permission in group.permissions" :key="permission.id">
          <input
            type="checkbox"
            :checked="draft.permission_ids.includes(permission.id)"
            @change="togglePermission(permission.id)"
          />
          {{ permission.name }}<em>{{ permission.code }}</em>
        </label>
      </div>
      <div class="actions">
        <button type="submit">{{ editing ? '保存' : '创建' }}</button>
        <button v-if="editing" type="button" @click="startCreate()">取消</button>
      </div>
    </form>
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

form {
  margin-top: var(--space-lg);
  padding: var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}

h2 {
  margin: 0 0 var(--space-md);
  font-size: 15px;
}

.fields {
  display: flex;
  gap: var(--space-sm);
  margin-bottom: var(--space-md);
}

input {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}

.group {
  margin-bottom: var(--space-md);
}

.group h3 {
  margin: 0 0 var(--space-sm);
  color: var(--color-text-weak);
  font-size: 12px;
  font-weight: 500;
}

.group label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-right: var(--space-md);
  font-size: 14px;
}

.group em {
  margin-left: 4px;
  color: var(--color-text-weak);
  font-size: 11px;
  font-style: normal;
}

.actions {
  display: flex;
  gap: var(--space-sm);
}

button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}

.muted {
  color: var(--color-text-weak);
}

.error {
  color: #d03050;
}
</style>
