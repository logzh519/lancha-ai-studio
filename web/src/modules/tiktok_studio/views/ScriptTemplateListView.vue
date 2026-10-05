<script setup lang="ts">
import { useSessionStore } from '@shared/core'
import { confirmDialog } from '@shared/ui'
import { computed, onMounted, ref } from 'vue'

import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  deleteScriptTemplate,
  listScriptTemplates,
  type ScriptTemplateSummary,
} from '../api'
import ScriptTemplateFormView from './ScriptTemplateFormView.vue'

const PAGE_SIZE = 20

const session = useSessionStore()

const templates = ref<ScriptTemplateSummary[]>([])
const total = ref(0)
const page = ref(1)
const error = ref('')
const keywordInput = ref('')
const keyword = ref('')
const jumpInput = ref(1)
const loading = ref(true)
const initialLoaded = ref(false)
const deletingId = ref<number | null>(null)
/** 抽屉打开时 id 为 null 表示新建 */
const drawer = ref<{ id: number | null } | null>(null)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function isOwner(template: ScriptTemplateSummary): boolean {
  if (session.user?.superuser) return true
  return template.created_by !== null && template.created_by === session.user?.id
}

async function onDrawerSaved(): Promise<void> {
  const created = drawer.value?.id === null
  drawer.value = null
  if (created) {
    keywordInput.value = ''
    keyword.value = ''
    await load(1)
  } else {
    await load(page.value)
  }
}

function search(): Promise<void> {
  keyword.value = keywordInput.value.trim()
  return load(1)
}

function jump(): Promise<void> {
  const target = Math.min(pageCount.value, Math.max(1, Math.trunc(Number(jumpInput.value)) || 1))
  return load(target)
}

async function load(target: number): Promise<void> {
  loading.value = true
  try {
    const result = await listScriptTemplates(target, PAGE_SIZE, keyword.value)
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
    if (target > lastPage) {
      await load(lastPage)
      return
    }
    templates.value = result.items
    page.value = target
    jumpInput.value = target
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
    initialLoaded.value = true
  }
}

async function remove(template: ScriptTemplateSummary): Promise<void> {
  if (!isOwner(template) || deletingId.value !== null) return
  const confirmed = await confirmDialog({
    title: '确认删除脚本',
    message: `确定删除脚本模版「${template.name}」？删除后将无法恢复。`,
    type: 'danger',
    confirmText: '确定删除',
    cancelText: '取消',
  })
  if (!confirmed) return
  deletingId.value = template.id
  try {
    await deleteScriptTemplate(template.id)
    templates.value = templates.value.filter((item) => item.id !== template.id)
    total.value = Math.max(0, total.value - 1)
    await load(page.value)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    deletingId.value = null
  }
}

onMounted(() => load(1))
</script>

<template>
  <div class="page-container">
    <!-- 面包屑与页头 -->
    <div class="page-header">
      <div class="header-titles">
        <div class="breadcrumb">
          <RouterLink to="/" class="breadcrumb-item">应用广场</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">TikTok 爆款脚本库</span>
        </div>
        <div class="title-with-badge">
          <h1>爆款视频脚本库</h1>
          <span v-if="initialLoaded" class="header-count-badge">共 {{ total }} 个模版</span>
        </div>
        <p class="header-desc">
          沉淀验证过的高转化短视频脚本结构与分镜节奏，提供多类目时长匹配与参考样片关联。
        </p>
      </div>

      <!-- 操作与搜索控制 -->
      <div class="header-actions">
        <form class="search-form" @submit.prevent="search">
          <div class="search-input-wrap">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="search-icon">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              v-model="keywordInput"
              type="search"
              maxlength="128"
              placeholder="按模板名称模糊搜索..."
              class="search-input"
            />
          </div>
          <button type="submit" class="btn-search">搜索</button>
        </form>

        <button
          v-permission="'tiktok_studio:script_template:create'"
          type="button"
          class="btn-primary"
          @click="drawer = { id: null }"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          <span>新建脚本</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="error-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- 表格卡片容器 -->
    <div class="table-card">
      <div class="table-scroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 80px;" class="text-center">ID</th>
              <th class="text-left">模板名称</th>
              <th>适合类目</th>
              <th>适合时长</th>
              <th>状态</th>
              <th>版本</th>
              <th>参考视频</th>
              <th>更新时间</th>
              <th style="width: 140px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !templates.length">
              <td colspan="9" class="table-loading">
                <div class="loading-wrap">
                  <span class="spinner"></span>
                  <span>正在加载脚本列表...</span>
                </div>
              </td>
            </tr>
            <tr v-for="template in templates" :key="template.id">
              <td class="text-center font-mono text-weak">#{{ template.id }}</td>
              <td class="font-bold text-main">
                <button type="button" class="name-link" @click="drawer = { id: template.id }">
                  {{ template.name }}
                </button>
              </td>
              <td class="text-center">
                <span class="badge-category">{{ CATEGORY_LABELS[template.category] || template.category }}</span>
              </td>
              <td class="text-center">
                <span class="duration-tag">
                  <svg viewBox="0 0 20 20" fill="currentColor" class="clock-icon">
                    <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm.75-13a.75.75 0 00-1.5 0v5c0 .414.336.75.75.75h4a.75.75 0 000-1.5h-3.25V5z" clip-rule="evenodd" />
                  </svg>
                  {{ template.duration_seconds }} 秒
                </span>
              </td>
              <td class="text-center">
                <span
                  class="badge-status"
                  :class="{
                    'status-formal': template.status === 'formal',
                    'status-test': template.status === 'test',
                  }"
                >
                  {{ STATUS_LABELS[template.status] || template.status }}
                </span>
              </td>
              <td class="text-center">
                <span class="version-tag">v{{ template.version }}</span>
              </td>
              <td class="text-center">
                <a
                  v-if="template.reference_video_url"
                  :href="template.reference_video_url"
                  target="_blank"
                  rel="noopener"
                  class="link-video"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" class="video-icon">
                    <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                  </svg>
                  <span>观看样片</span>
                </a>
                <span v-else class="text-weak">—</span>
              </td>
              <td class="text-center text-weak text-sm">{{ new Date(template.updated_at).toLocaleString() }}</td>
              <td class="table-actions text-center">
                <template v-if="isOwner(template)">
                  <button
                    type="button"
                    class="action-link"
                    :disabled="deletingId !== null"
                    @click="drawer = { id: template.id }"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    class="action-link danger"
                    :disabled="deletingId !== null"
                    @click="remove(template)"
                  >
                    {{ deletingId === template.id ? '删除中...' : '删除' }}
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="action-link"
                    :disabled="deletingId !== null"
                    @click="drawer = { id: template.id }"
                  >
                    查看
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="initialLoaded && !loading && !templates.length && !error">
              <td colspan="9" class="table-empty">
                <div class="empty-wrap">
                  <span class="empty-icon-text">📄</span>
                  <p>{{ keyword ? '没有匹配的爆款脚本' : '当前暂无脚本模板' }}</p>
                  <button
                    v-if="!keyword"
                    v-permission="'tiktok_studio:script_template:create'"
                    type="button"
                    class="btn-primary btn-sm"
                    @click="drawer = { id: null }"
                  >
                    新建第一个脚本
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页栏 -->
      <footer v-if="initialLoaded && (templates.length > 0 || total > 0)" class="table-pager">
        <span class="pager-total">共 {{ total }} 条记录</span>
        <div class="pager-controls">
          <button
            type="button"
            class="pager-btn"
            :disabled="page <= 1"
            @click="load(page - 1)"
          >
            上一页
          </button>
          <span class="pager-indicator">第 {{ page }} / {{ pageCount }} 页</span>
          <button
            type="button"
            class="pager-btn"
            :disabled="page >= pageCount"
            @click="load(page + 1)"
          >
            下一页
          </button>
        </div>
        <form class="pager-jump" @submit.prevent="jump">
          <span>跳至</span>
          <input
            v-model.number="jumpInput"
            type="number"
            min="1"
            :max="pageCount"
            class="jump-input"
          />
          <span>页</span>
          <button type="submit" class="pager-btn">跳转</button>
        </form>
      </footer>
    </div>

    <Teleport to="body">
      <Transition name="drawer">
        <div v-if="drawer" class="drawer-overlay" role="dialog" aria-modal="true">
          <aside class="drawer-panel">
            <ScriptTemplateFormView
              :id="drawer.id"
              :key="drawer.id ?? 'new'"
              @close="drawer = null"
              @saved="onDrawerSaved"
            />
          </aside>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.page-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: var(--space-md);
}

/* 页头 */
.page-header {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: 20px 24px;
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

/* 头部操作 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search-form {
  display: flex;
  align-items: center;
  gap: 8px;
}

.search-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 10px;
  width: 15px;
  height: 15px;
  color: var(--color-text-weak);
  pointer-events: none;
}

.search-input {
  width: 220px;
  height: 36px;
  padding: 0 12px 0 32px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 13px;
  color: var(--color-text);
  outline: none;
  transition: all var(--transition-fast);
}

.search-input:focus {
  background: var(--color-surface);
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.btn-search {
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-search:hover {
  background: var(--color-surface-subtle);
  border-color: var(--color-border-hover);
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
  text-decoration: none;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  transition: all var(--transition-fast);
}

.btn-primary:hover {
  background: var(--color-primary-hover);
}

.btn-sm {
  height: 32px;
  padding: 0 12px;
  font-size: 12px;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

/* 错误条目 */
.error-banner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-danger-light);
  border: 1px solid #fecaca;
  border-radius: var(--radius);
  color: var(--color-danger-text);
  font-size: 13px;
}

.error-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* 数据卡片与表格 */
.table-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

.table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.data-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  white-space: nowrap;
  text-align: center;
}

.data-table tbody td {
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-subtle);
  vertical-align: middle;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:hover td {
  background: #fbfcfe;
}

.font-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.font-bold {
  font-weight: 600;
}

.text-weak {
  color: var(--color-text-weak);
}

.text-main {
  color: var(--color-text);
}

.text-sm {
  font-size: 12px;
}

.text-left {
  text-align: left !important;
}

.text-center {
  text-align: center !important;
}

.name-link {
  padding: 0;
  border: none;
  background: transparent;
  font: inherit;
  color: var(--color-text);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.name-link:hover {
  color: var(--color-primary);
}

/* 徽标 */
.badge-category {
  display: inline-block;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: #f1f5f9;
  color: #334155;
  border: 1px solid #e2e8f0;
}

.duration-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-muted);
}

.clock-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-weak);
}

.badge-status {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
}

.status-formal {
  background: var(--color-success-light);
  color: var(--color-success-text);
  border: 1px solid #a7f3d0;
}

.status-test {
  background: var(--color-warning-light);
  color: var(--color-warning-text);
  border: 1px solid #fde68a;
}

.version-tag {
  font-size: 11px;
  font-family: monospace;
  padding: 2px 6px;
  background: var(--color-surface-subtle);
  border-radius: var(--radius-sm);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border-subtle);
}

.link-video {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-primary);
  font-weight: 500;
  transition: color var(--transition-fast);
}

.link-video:hover {
  text-decoration: underline;
  color: var(--color-primary-hover);
}

.video-icon {
  width: 13px;
  height: 13px;
}

.table-actions {
  text-align: center;
  white-space: nowrap;
}

.action-link {
  display: inline-block;
  padding: 4px 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-primary);
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.action-link:hover:not(:disabled) {
  background: var(--color-primary-light);
}

.action-link.danger {
  color: var(--color-danger);
}

.action-link.danger:hover:not(:disabled) {
  background: var(--color-danger-light);
}

.action-link:disabled,
.action-link.disabled {
  color: var(--color-text-weak) !important;
  opacity: 0.4;
  cursor: not-allowed;
  pointer-events: auto;
  background: transparent !important;
}

/* 空状态与加载中 */
.table-loading,
.table-empty {
  text-align: center;
  padding: 48px 16px !important;
}

.loading-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--color-text-weak);
  font-size: 13px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.empty-icon-text {
  font-size: 32px;
}

.empty-wrap p {
  margin: 0;
  color: var(--color-text-weak);
  font-size: 13px;
}

/* 分页栏 */
.table-pager {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-lg);
  padding: 12px 20px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  font-size: 13px;
}

.pager-total {
  color: var(--color-text-weak);
  margin-right: auto;
}

.pager-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pager-indicator {
  color: var(--color-text-muted);
  font-weight: 500;
  padding: 0 4px;
}

.pager-btn {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 12px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.pager-btn:hover:not(:disabled) {
  background: var(--color-surface-subtle);
  border-color: var(--color-border-hover);
}

.pager-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.pager-jump {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-muted);
  font-size: 12px;
}

.jump-input {
  width: 52px;
  height: 30px;
  padding: 0 6px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  text-align: center;
  font-size: 12px;
}

/* 编辑抽屉 */
.drawer-overlay {
  position: fixed;
  inset: 0;
  z-index: 9500;
  display: flex;
  justify-content: flex-end;
  background: rgba(15, 23, 42, 0.45);
}

.drawer-panel {
  width: min(960px, 100vw);
  height: 100%;
  overflow-y: auto;
  padding: 0 var(--space-md) var(--space-md);
  background: var(--color-bg, #f8fafc);
  box-shadow: -12px 0 32px rgba(15, 23, 42, 0.18);
}

.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.2s ease;
}

.drawer-enter-active .drawer-panel,
.drawer-leave-active .drawer-panel {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}

.drawer-enter-from .drawer-panel,
.drawer-leave-to .drawer-panel {
  transform: translateX(100%);
}
</style>
