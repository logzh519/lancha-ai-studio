<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { createItem, listItems, type Item } from '../api'

const items = ref<Item[]>([])
const name = ref('')
const error = ref('')
const submitting = ref(false)

async function refresh(): Promise<void> {
  try {
    items.value = await listItems()
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function submit(): Promise<void> {
  if (!name.value.trim() || submitting.value) return
  submitting.value = true
  try {
    await createItem(name.value.trim())
    name.value = ''
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    submitting.value = false
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
          <span class="breadcrumb-current">示例模块 A</span>
        </div>
        <div class="title-with-badge">
          <h1>Example A · 条目管理</h1>
          <span class="header-count-badge">已记录 {{ items.length }} 项</span>
        </div>
        <p class="header-desc">
          演示标准业务模块的单体增删与基于进程内事件总线（EventBus）的消息发布机制。
        </p>
      </div>

      <div class="header-actions">
        <button type="button" class="btn-refresh" @click="refresh">
          <svg viewBox="0 0 20 20" fill="currentColor" class="refresh-icon">
            <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
          </svg>
          <span>刷新</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="banner-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- 录入与操作卡片 -->
    <div class="content-card">
      <form v-permission="'example_a:item:create'" class="entry-form" @submit.prevent="submit">
        <input
          v-model="name"
          placeholder="请输入条目名称并提交..."
          class="form-control"
          required
        />
        <button type="submit" class="btn-primary" :disabled="submitting">
          {{ submitting ? '提交中...' : '新增条目' }}
        </button>
      </form>

      <div class="list-container">
        <div v-if="items.length > 0" class="item-grid">
          <div v-for="item in items" :key="item.id" class="item-card">
            <div class="item-id">#{{ item.id }}</div>
            <div class="item-name">{{ item.name }}</div>
          </div>
        </div>
        <div v-else class="empty-box">暂无条目数据</div>
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

.content-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.entry-form {
  display: flex;
  gap: 10px;
}

.form-control {
  flex: 1;
  max-width: 360px;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font-size: 13px;
  outline: none;
  transition: all var(--transition-fast);
}

.form-control:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 38px;
  padding: 0 18px;
  background: var(--color-primary);
  color: #ffffff;
  border: none;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.item-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.item-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  background: var(--color-surface-subtle);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius);
  font-size: 13px;
}

.item-id {
  font-family: monospace;
  color: var(--color-text-weak);
  font-size: 12px;
}

.item-name {
  font-weight: 500;
  color: var(--color-text);
}

.empty-box {
  text-align: center;
  color: var(--color-text-weak);
  font-size: 13px;
  padding: 40px 16px;
}
</style>
