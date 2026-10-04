<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { listReceivedEvents, type ReceivedItem } from '../api'

const received = ref<ReceivedItem[]>([])
const error = ref('')

async function refresh(): Promise<void> {
  try {
    received.value = await listReceivedEvents()
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
          <span class="breadcrumb-current">示例模块 B</span>
        </div>
        <div class="title-with-badge">
          <h1>Example B · 事件收件箱</h1>
          <span class="header-count-badge">已捕获 {{ received.length }} 条事件</span>
        </div>
        <p class="header-desc">
          演示进程内同步派发的事件消费监听机制，接收由 Example A 或其他服务广播的生命周期事件。
        </p>
      </div>

      <div class="header-actions">
        <button type="button" class="btn-refresh" @click="refresh">
          <svg viewBox="0 0 20 20" fill="currentColor" class="refresh-icon">
            <path fill-rule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clip-rule="evenodd" />
          </svg>
          <span>拉取最新事件</span>
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="banner-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- 事件列表卡片 -->
    <div class="content-card">
      <div v-if="received.length > 0" class="events-list">
        <div
          v-for="(event, index) in received"
          :key="`${event.item_id}-${index}`"
          class="event-row"
        >
          <div class="event-badge">
            <span class="event-dot"></span>
            <span class="event-type">example_a.item_created</span>
          </div>
          <div class="event-payload">
            <span class="payload-id">#{{ event.item_id }}</span>
            <span class="payload-name">{{ event.name }}</span>
          </div>
          <span class="event-tag">已捕获</span>
        </div>
      </div>
      <div v-else class="empty-box">尚未收到任何广播条目事件</div>
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
  overflow: hidden;
}

.events-list {
  display: flex;
  flex-direction: column;
}

.event-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--color-border-subtle);
  transition: background var(--transition-fast);
}

.event-row:last-child {
  border-bottom: none;
}

.event-row:hover {
  background: var(--color-surface-subtle);
}

.event-badge {
  display: flex;
  align-items: center;
  gap: 8px;
}

.event-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-success);
}

.event-type {
  font-family: monospace;
  font-size: 12px;
  color: var(--color-primary);
  font-weight: 600;
}

.event-payload {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  flex: 1;
}

.payload-id {
  font-family: monospace;
  color: var(--color-text-weak);
}

.payload-name {
  color: var(--color-text);
  font-weight: 500;
}

.event-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
  border: 1px solid var(--color-border-subtle);
}

.empty-box {
  text-align: center;
  color: var(--color-text-weak);
  font-size: 13px;
  padding: 48px 16px;
}
</style>
