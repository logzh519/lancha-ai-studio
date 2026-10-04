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
  if (!window.confirm(`删除角色「${role.name}」将收回 ${role.user_count} 个用户的对应权限，且无法撤销。确定吗？`)) return
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
  <div class="page-container">
    <div class="page-header">
      <div class="header-titles">
        <div class="breadcrumb">
          <RouterLink to="/" class="breadcrumb-item">应用广场</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">角色权限管理</span>
        </div>
        <div class="title-with-badge">
          <h1>系统角色与权限</h1>
          <span class="header-count-badge">已配置 {{ roles.length }} 个角色</span>
        </div>
        <p class="header-desc">
          定义业务角色身份及其绑定的功能权限码，保障团队协作中的最小特权与数据操作合规。
        </p>
      </div>

      <div class="header-actions">
        <button
          v-if="canManage"
          type="button"
          class="btn-primary"
          @click="startCreate"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          <span>新建角色</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="banner-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- 角色列表卡片 -->
    <div class="table-card">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th>角色名称</th>
              <th>唯一标识码</th>
              <th>包含权限点</th>
              <th>已关联成员数</th>
              <th>角色描述</th>
              <th style="text-align: right; width: 140px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="role in roles" :key="role.id">
              <td class="font-bold text-main">{{ role.name }}</td>
              <td class="font-mono text-weak">{{ role.code }}</td>
              <td>
                <span class="count-tag">{{ role.permission_ids.length }} 项权限</span>
              </td>
              <td>
                <span class="user-count-tag">{{ role.user_count }} 人</span>
              </td>
              <td class="text-muted text-sm">{{ role.description || '—' }}</td>
              <td class="table-actions">
                <button
                  type="button"
                  class="action-btn"
                  :disabled="!canManage"
                  @click="startEdit(role)"
                >
                  编辑
                </button>
                <button
                  type="button"
                  class="action-btn danger"
                  :disabled="!canManage"
                  @click="remove(role)"
                >
                  删除
                </button>
              </td>
            </tr>
            <tr v-if="roles.length === 0 && !error">
              <td colspan="6" class="table-empty">暂无角色记录</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 角色配置表单 -->
    <form v-if="canManage" class="role-form-card" @submit.prevent="submit">
      <div class="form-header-bar">
        <h2>{{ editing ? `编辑角色：${editing.name}` : '新建角色定义' }}</h2>
        <span class="form-subtitle">配置角色基础属性与权限点映射</span>
      </div>

      <div class="form-fields">
        <div class="input-group">
          <label class="input-label required">角色标识</label>
          <input
            v-model="draft.code"
            :disabled="!!editing"
            placeholder="例如 ops"
            required
            class="input-control"
          />
        </div>
        <div class="input-group">
          <label class="input-label required">角色名称</label>
          <input
            v-model="draft.name"
            placeholder="例如 运营专员"
            required
            class="input-control"
          />
        </div>
        <div class="input-group full-width">
          <label class="input-label">说明描述（可选）</label>
          <input
            v-model="draft.description"
            placeholder="角色职责范围与权限归属说明"
            class="input-control"
          />
        </div>
      </div>

      <!-- 权限点矩阵 -->
      <div class="permissions-matrix">
        <h3 class="matrix-title">分配权限范围</h3>
        <div class="matrix-groups">
          <div v-for="group in groups" :key="group.module" class="matrix-group">
            <h4 class="group-title">
              <span class="group-icon">📦</span>
              <span>模块：{{ group.module }}</span>
            </h4>
            <div class="perm-chips">
              <label
                v-for="permission in group.permissions"
                :key="permission.id"
                class="perm-chip"
                :class="{ 'chip-selected': draft.permission_ids.includes(permission.id) }"
              >
                <input
                  type="checkbox"
                  :checked="draft.permission_ids.includes(permission.id)"
                  @change="togglePermission(permission.id)"
                />
                <span class="perm-name">{{ permission.name }}</span>
                <span class="perm-code">{{ permission.code }}</span>
              </label>
            </div>
          </div>
        </div>
      </div>

      <div class="form-actions-bar">
        <button v-if="editing" type="button" class="btn-cancel" @click="startCreate()">取消</button>
        <button type="submit" class="btn-primary">{{ editing ? '保存修改' : '创建角色' }}</button>
      </div>
    </form>
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

.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 16px;
  background: var(--color-primary);
  color: #ffffff;
  border: none;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.btn-cancel {
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-cancel:hover {
  background: var(--color-surface-subtle);
  color: var(--color-text);
}

/* 提示条 */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  background: var(--color-danger-light);
  border: 1px solid #fecaca;
  color: var(--color-danger-text);
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

.font-bold {
  font-weight: 600;
}

.text-main {
  color: var(--color-text);
}

.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.text-weak {
  color: var(--color-text-weak);
}

.text-muted {
  color: var(--color-text-muted);
}

.text-sm {
  font-size: 12px;
}

.count-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-primary-border);
}

.user-count-tag {
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  background: #f1f5f9;
  color: #475569;
  border-radius: var(--radius-sm);
  border: 1px solid #e2e8f0;
}

.table-actions {
  text-align: right;
  white-space: nowrap;
}

.action-btn {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-btn:hover:not(:disabled) {
  background: var(--color-primary-light);
}

.action-btn.danger {
  color: var(--color-danger);
}

.action-btn.danger:hover:not(:disabled) {
  background: var(--color-danger-light);
}

.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.table-empty {
  text-align: center;
  color: var(--color-text-weak);
  padding: 32px 16px !important;
}

/* 角色配置表单 */
.role-form-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.form-header-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--color-border-subtle);
}

.form-header-bar h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text);
}

.form-subtitle {
  font-size: 12px;
  color: var(--color-text-weak);
}

.form-fields {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px 20px;
}

.full-width {
  grid-column: span 2;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.input-label.required::after {
  content: ' *';
  color: var(--color-danger);
}

.input-control {
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  outline: none;
  transition: all var(--transition-fast);
}

.input-control:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.input-control:disabled {
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
}

/* 权限矩阵 */
.permissions-matrix {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-top: 10px;
}

.matrix-title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text);
}

.matrix-groups {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.matrix-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  background: var(--color-surface-subtle);
  border-radius: var(--radius);
  border: 1px solid var(--color-border-subtle);
}

.group-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-muted);
}

.group-icon {
  font-size: 14px;
}

.perm-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.perm-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.perm-chip:hover {
  border-color: var(--color-border-hover);
}

.chip-selected {
  background: var(--color-primary-light);
  border-color: var(--color-primary-border);
}

.perm-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text);
}

.chip-selected .perm-name {
  color: var(--color-primary);
}

.perm-code {
  font-size: 11px;
  font-family: monospace;
  color: var(--color-text-weak);
}

.chip-selected .perm-code {
  color: #3b82f6;
}

.form-actions-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 14px;
  border-top: 1px solid var(--color-border-subtle);
}
</style>
