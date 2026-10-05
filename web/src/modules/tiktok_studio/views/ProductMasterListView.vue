<script setup lang="ts">
import { useSessionStore } from '@shared/core'
import { ConfirmDialog, confirmDialog } from '@shared/ui'
import { computed, onMounted, onUnmounted, ref } from 'vue'

import {
  deleteProductMaster,
  IMPORT_STATUS_LABELS,
  importProductMasters,
  type ImportStage,
  type ImportStatus,
  listProductMasters,
  type ProductMasterSummary,
  retryProductImport,
  type StageTrace,
} from '../api'
import ProductMasterFormView from './ProductMasterFormView.vue'

const PAGE_SIZE = 20
const MAX_IMPORT_SKUS = 50
const POLL_INTERVAL_MS = 5000
const PREVIEW_DELAY_MS = 500
const PREVIEW_MAX_HEIGHT = 492
const TRACE_WIDTH = 480
const TRACE_MAX_HEIGHT = 420
const TRACE_HIDE_DELAY_MS = 150
const IMPORT_STAGES: { key: ImportStage; label: string }[] = [
  { key: 'crawl', label: '详情' },
  { key: 'view', label: '三视图参考图' },
  { key: 'gen', label: '生成三视图' },
]

const session = useSessionStore()

const products = ref<ProductMasterSummary[]>([])
const total = ref(0)
const page = ref(1)
const error = ref('')
const keywordInput = ref('')
const keyword = ref('')
const jumpInput = ref(1)
const loading = ref(true)
const initialLoaded = ref(false)
const deletingIds = ref(new Set<number>())
const retryingId = ref<number | null>(null)
const importOpen = ref(false)
const importInput = ref('')
const importError = ref('')
const importNotice = ref('')
const importing = ref(false)
const drawerId = ref<number | null>(null)
let pollTimer: ReturnType<typeof setTimeout> | undefined
const preview = ref<{ url: string; top: number; left: number } | null>(null)
let previewTimer: ReturnType<typeof setTimeout> | undefined

function schedulePreview(event: MouseEvent, url: string): void {
  clearTimeout(previewTimer)
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  previewTimer = setTimeout(() => {
    const centered = rect.top + rect.height / 2 - PREVIEW_MAX_HEIGHT / 2
    const top = Math.max(8, Math.min(centered, window.innerHeight - PREVIEW_MAX_HEIGHT - 8))
    preview.value = { url, top, left: rect.right + 12 }
  }, PREVIEW_DELAY_MS)
}

function hidePreview(): void {
  clearTimeout(previewTimer)
  preview.value = null
}

interface TracePopover {
  label: string
  /** 旧数据没有现场记录时只有错误信息 */
  trace: StageTrace | null
  error: string
  top: number
  left: number
}

const tracePopover = ref<TracePopover | null>(null)
let traceTimer: ReturnType<typeof setTimeout> | undefined

function stageStatus(product: ProductMasterSummary, stage: ImportStage): ImportStatus | null {
  return product[`${stage}_status`]
}

function showTrace(event: MouseEvent, product: ProductMasterSummary, stage: ImportStage, label: string): void {
  clearTimeout(traceTimer)
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const below = rect.bottom + 6
  tracePopover.value = {
    label,
    trace: product.import_trace[stage] ?? null,
    error: product[`${stage}_error`] ?? '',
    top: below + TRACE_MAX_HEIGHT <= window.innerHeight - 8 ? below : Math.max(8, rect.top - 6 - TRACE_MAX_HEIGHT),
    left: Math.max(8, Math.min(rect.left, window.innerWidth - TRACE_WIDTH - 8)),
  }
}

function keepTrace(): void {
  clearTimeout(traceTimer)
}

function hideTrace(delay = TRACE_HIDE_DELAY_MS): void {
  clearTimeout(traceTimer)
  traceTimer = setTimeout(() => (tracePopover.value = null), delay)
}

function formatJson(value: Record<string, unknown>): string {
  return Object.keys(value).length ? JSON.stringify(value, null, 2) : '无'
}

function onTableScroll(): void {
  hidePreview()
  hideTrace(0)
}

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const importSkus = computed(() => [
  ...new Set(
    importInput.value
      .split(/[;；,，\s]+/)
      .map((sku) => sku.trim().toUpperCase())
      .filter(Boolean),
  ),
])

function statusLabel(status: ImportStatus | null): string {
  return status ? IMPORT_STATUS_LABELS[status] : '—'
}

function isImportBusy(product: ProductMasterSummary): boolean {
  return [product.crawl_status, product.view_status, product.gen_status].some(
    (s) => s === 'pending' || s === 'running',
  )
}

function hasImportFailure(product: ProductMasterSummary): boolean {
  return [product.crawl_status, product.view_status, product.gen_status].includes('failed')
}

function schedulePoll(): void {
  clearTimeout(pollTimer)
  if (products.value.some(isImportBusy)) {
    pollTimer = setTimeout(() => load(page.value), POLL_INTERVAL_MS)
  }
}

function openImport(): void {
  importInput.value = ''
  importError.value = ''
  importOpen.value = true
}

async function submitImport(): Promise<void> {
  if (importing.value) return
  const skus = importSkus.value
  if (!skus.length) {
    importError.value = '请至少填写一个货号'
    return
  }
  if (skus.length > MAX_IMPORT_SKUS) {
    importError.value = `单次最多导入 ${MAX_IMPORT_SKUS} 个货号，当前 ${skus.length} 个`
    return
  }
  importing.value = true
  importError.value = ''
  try {
    const result = await importProductMasters(skus)
    const parts = [`新增 ${result.created.length} 条`, `已存在跳过 ${result.skipped} 条`]
    if (result.failed.length) parts.push(`失败 ${result.failed.length} 个：${result.failed.map((f) => f.message).join('；')}`)
    importNotice.value = `导入完成：${parts.join('，')}。详情与三视图将在后台补全。`
    importOpen.value = false
    keywordInput.value = ''
    keyword.value = ''
    await load(1)
  } catch (e) {
    importError.value = (e as Error).message
  } finally {
    importing.value = false
  }
}

async function retry(product: ProductMasterSummary): Promise<void> {
  if (retryingId.value !== null) return
  retryingId.value = product.id
  try {
    await retryProductImport(product.id)
    await load(page.value)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    retryingId.value = null
  }
}

function openDrawer(product: ProductMasterSummary): void {
  hidePreview()
  hideTrace(0)
  drawerId.value = product.id
}

async function onDrawerSaved(): Promise<void> {
  drawerId.value = null
  await load(page.value)
}

function isOwner(product: ProductMasterSummary): boolean {
  if (session.user?.superuser) return true
  return product.created_by !== null && product.created_by === session.user?.id
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
  clearTimeout(pollTimer)
  loading.value = true
  try {
    const result = await listProductMasters(target, PAGE_SIZE, keyword.value)
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
    if (target > lastPage) {
      await load(lastPage)
      return
    }
    products.value = result.items
    page.value = target
    jumpInput.value = target
    error.value = ''
    schedulePoll()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
    initialLoaded.value = true
  }
}

async function remove(product: ProductMasterSummary): Promise<void> {
  if (!isOwner(product) || deletingIds.value.has(product.id)) return
  const confirmed = await confirmDialog({
    title: '确认删除商品',
    message: `确定删除商品「${product.sku}」？删除后将无法恢复。`,
    type: 'danger',
    confirmText: '确定删除',
    cancelText: '取消',
  })
  if (!confirmed) return
  deletingIds.value.add(product.id)
  try {
    await deleteProductMaster(product.id)
    products.value = products.value.filter((item) => item.id !== product.id)
    total.value = Math.max(0, total.value - 1)
    await load(page.value)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    deletingIds.value.delete(product.id)
  }
}

onMounted(() => load(1))
onUnmounted(() => {
  clearTimeout(pollTimer)
  clearTimeout(previewTimer)
  clearTimeout(traceTimer)
})
</script>

<template>
  <div class="page-container">
    <!-- 面包屑与页头 -->
    <div class="page-header">
      <div class="header-titles">
        <div class="breadcrumb">
          <RouterLink to="/" class="breadcrumb-item">应用广场</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">TikTok 商品资产库</span>
        </div>
        <div class="title-with-badge">
          <h1>商品资产库</h1>
          <span v-if="initialLoaded" class="header-count-badge">共 {{ total }} 个商品</span>
        </div>
        <p class="header-desc">
          统一管理商品基础信息、卖点描述及主图、副图、三视图等素材资产，供视频脚本与素材生产复用。
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
              placeholder="按货号 / ASIN / PID 搜索..."
              class="search-input"
            />
          </div>
          <button type="submit" class="btn-search">搜索</button>
        </form>

        <button
          v-permission="'tiktok_studio:product_master:create'"
          type="button"
          class="btn-secondary"
          @click="openImport"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
            <path d="M10.75 2.75a.75.75 0 00-1.5 0v8.614L6.295 8.235a.75.75 0 10-1.09 1.03l4.25 4.5a.75.75 0 001.09 0l4.25-4.5a.75.75 0 00-1.09-1.03l-2.955 3.129V2.75z" />
            <path d="M3.5 12.75a.75.75 0 00-1.5 0v2.5A2.75 2.75 0 004.75 18h10.5A2.75 2.75 0 0018 15.25v-2.5a.75.75 0 00-1.5 0v2.5c0 .69-.56 1.25-1.25 1.25H4.75c-.69 0-1.25-.56-1.25-1.25v-2.5z" />
          </svg>
          <span>批量导入</span>
        </button>

        <RouterLink
          v-permission="'tiktok_studio:product_master:create'"
          to="/tiktok_studio/product-masters/new"
          class="btn-primary"
        >
          <svg viewBox="0 0 20 20" fill="currentColor" class="btn-icon">
            <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
          </svg>
          <span>新建商品</span>
        </RouterLink>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="error-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <div v-if="importNotice" class="notice-banner">
      <span>{{ importNotice }}</span>
      <button type="button" class="notice-close" aria-label="关闭" @click="importNotice = ''">×</button>
    </div>

    <!-- 表格卡片容器 -->
    <div class="table-card">
      <div class="table-scroll" @scroll="onTableScroll">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 80px;" class="text-center">ID</th>
              <th>主图</th>
              <th class="text-left">产品货号</th>
              <th>ASIN</th>
              <th>颜色</th>
              <th>销售店铺</th>
              <th>PID</th>
              <th>类目</th>
              <th>导入状态</th>
              <th>更新时间</th>
              <th style="width: 160px;">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !products.length">
              <td colspan="11" class="table-loading">
                <div class="loading-wrap">
                  <span class="spinner"></span>
                  <span>正在加载商品列表...</span>
                </div>
              </td>
            </tr>
            <tr v-for="product in products" :key="product.id">
              <td class="text-center font-mono text-weak">#{{ product.id }}</td>
              <td class="text-center">
                <a
                  v-if="product.main_image?.url"
                  :href="product.main_image.url"
                  target="_blank"
                  rel="noopener"
                  class="thumb"
                  @mouseenter="schedulePreview($event, product.main_image.url)"
                  @mouseleave="hidePreview"
                >
                  <img :src="product.main_image.url" alt="" />
                </a>
                <span v-else class="text-weak">—</span>
              </td>
              <td class="font-bold text-main">
                <button type="button" class="name-link" @click="openDrawer(product)">
                  {{ product.sku }}
                </button>
              </td>
              <td class="text-center font-mono">{{ product.asin || '—' }}</td>
              <td class="text-center">{{ product.color || '—' }}</td>
              <td class="text-center">{{ product.store || '—' }}</td>
              <td class="text-center font-mono">{{ product.pid || '—' }}</td>
              <td class="text-center">{{ product.category || '—' }}</td>
              <td class="text-center">
                <div v-if="product.crawl_status" class="import-steps">
                  <template v-for="(stage, index) in IMPORT_STAGES" :key="stage.key">
                    <span v-if="index > 0" class="step-arrow">→</span>
                    <span
                      class="status-tag"
                      :class="`is-${stageStatus(product, stage.key) ?? 'none'}`"
                      :title="stageStatus(product, stage.key) === 'failed' ? undefined : statusLabel(stageStatus(product, stage.key))"
                      @mouseenter="stageStatus(product, stage.key) === 'failed' && showTrace($event, product, stage.key, stage.label)"
                      @mouseleave="hideTrace()"
                    >
                      {{ stage.label }}
                    </span>
                  </template>
                </div>
                <span v-else class="text-weak">—</span>
              </td>
              <td class="text-center text-weak text-sm">{{ new Date(product.updated_at).toLocaleString() }}</td>
              <td class="table-actions text-center">
                <template v-if="isOwner(product)">
                  <button
                    v-if="hasImportFailure(product)"
                    v-permission="'tiktok_studio:product_master:create'"
                    type="button"
                    class="action-link"
                    :disabled="retryingId !== null"
                    @click="retry(product)"
                  >
                    {{ retryingId === product.id ? '重试中...' : '重试' }}
                  </button>
                  <button
                    type="button"
                    class="action-link"
                    :disabled="deletingIds.has(product.id)"
                    @click="openDrawer(product)"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    class="action-link danger"
                    :disabled="deletingIds.has(product.id)"
                    @click="remove(product)"
                  >
                    {{ deletingIds.has(product.id) ? '删除中...' : '删除' }}
                  </button>
                </template>
                <template v-else>
                  <button
                    type="button"
                    class="action-link"
                    :disabled="deletingIds.has(product.id)"
                    @click="openDrawer(product)"
                  >
                    查看
                  </button>
                </template>
              </td>
            </tr>
            <tr v-if="initialLoaded && !loading && !products.length && !error">
              <td colspan="11" class="table-empty">
                <div class="empty-wrap">
                  <span class="empty-icon-text">📦</span>
                  <p>{{ keyword ? '没有匹配的商品' : '当前暂无商品资产' }}</p>
                  <RouterLink
                    v-if="!keyword"
                    v-permission="'tiktok_studio:product_master:create'"
                    to="/tiktok_studio/product-masters/new"
                    class="btn-primary btn-sm"
                  >
                    新建第一个商品
                  </RouterLink>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页栏 -->
      <footer v-if="initialLoaded && (products.length > 0 || total > 0)" class="table-pager">
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
      <div
        v-if="preview"
        class="image-preview"
        :style="{ top: `${preview.top}px`, left: `${preview.left}px` }"
      >
        <img :src="preview.url" alt="" />
      </div>
      <div
        v-if="tracePopover"
        class="trace-popover"
        :style="{ top: `${tracePopover.top}px`, left: `${tracePopover.left}px`, width: `${TRACE_WIDTH}px`, maxHeight: `${TRACE_MAX_HEIGHT}px` }"
        @mouseenter="keepTrace"
        @mouseleave="hideTrace()"
      >
        <div class="trace-title">{{ tracePopover.label }} · 失败</div>
        <dl class="trace-body">
          <dt>错误信息</dt>
          <dd class="trace-error">
            <span v-if="tracePopover.trace?.error_code" class="trace-code">{{ tracePopover.trace.error_code }}</span>
            {{ tracePopover.trace?.error_message ?? (tracePopover.error || '无') }}
          </dd>
          <template v-if="tracePopover.trace">
            <dt>输入</dt>
            <dd><pre>{{ formatJson(tracePopover.trace.input) }}</pre></dd>
            <dt>输出</dt>
            <dd><pre>{{ formatJson(tracePopover.trace.output) }}</pre></dd>
          </template>
        </dl>
      </div>
      <Transition name="drawer">
        <div v-if="drawerId !== null" class="drawer-overlay" role="dialog" aria-modal="true">
          <aside class="drawer-panel">
            <ProductMasterFormView
              :id="drawerId"
              :key="drawerId"
              @close="drawerId = null"
              @regenerated="load(page)"
              @saved="onDrawerSaved"
            />
          </aside>
        </div>
      </Transition>
    </Teleport>

    <ConfirmDialog
      v-model:open="importOpen"
      title="批量导入商品"
      type="info"
      confirm-text="开始导入"
      :confirm-loading="importing"
      :close-on-click-overlay="false"
      @confirm="submitImport"
    >
      <div class="import-form">
        <textarea
          v-model="importInput"
          rows="6"
          class="import-textarea"
          placeholder="输入产品货号，多个用分号、逗号或换行分隔，如：WTK9167; WTC2835"
          :disabled="importing"
        ></textarea>
        <p class="import-hint">
          已识别 {{ importSkus.length }} 个货号（单次最多 {{ MAX_IMPORT_SKUS }} 个）。基础信息立即入库，详情、主副图与三视图在后台补全。
        </p>
        <p v-if="importError" class="import-error">{{ importError }}</p>
      </div>
    </ConfirmDialog>
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

/* 主图缩略图 */
.thumb {
  display: inline-block;
  width: 48px;
  height: 64px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: #ffffff;
  overflow: hidden;
  vertical-align: middle;
  cursor: zoom-in;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.image-preview {
  position: fixed;
  z-index: 9000;
  padding: 6px;
  background: #ffffff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
  pointer-events: none;
}

.image-preview img {
  display: block;
  max-width: 360px;
  max-height: 480px;
  object-fit: contain;
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

/* 批量导入 */
.btn-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius);
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-secondary:hover {
  background: var(--color-surface);
}

.notice-banner {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-primary-light);
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius);
  color: var(--color-primary);
  font-size: 13px;
  line-height: 1.5;
}

.notice-banner span {
  flex: 1;
  word-break: break-word;
}

.notice-close {
  border: none;
  background: transparent;
  color: inherit;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
}

.import-steps {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.step-arrow {
  color: var(--color-text-weak);
  font-size: 11px;
}

.status-tag {
  display: inline-block;
  padding: 1px 8px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 500;
  white-space: nowrap;
}

.status-tag.is-running {
  background: var(--color-primary-light);
  border-color: var(--color-primary-border);
  color: var(--color-primary);
}

.status-tag.is-done {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #15803d;
}

.status-tag.is-failed {
  background: var(--color-danger-light);
  border-color: #fecaca;
  color: var(--color-danger-text);
  cursor: help;
}

.trace-popover {
  position: fixed;
  z-index: 9000;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
  overflow: hidden;
  font-size: 12px;
}

.trace-title {
  flex-shrink: 0;
  padding: 8px 12px;
  background: var(--color-danger-light);
  color: var(--color-danger-text);
  font-weight: 600;
}

.trace-body {
  margin: 0;
  padding: 8px 12px 12px;
  overflow: auto;
}

.trace-body dt {
  margin-top: 8px;
  color: var(--color-text-muted);
  font-weight: 600;
}

.trace-body dd {
  margin: 4px 0 0;
  color: var(--color-text);
  word-break: break-word;
}

.trace-body pre {
  margin: 0;
  padding: 8px;
  background: var(--color-surface-subtle);
  border-radius: var(--radius-sm);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  white-space: pre-wrap;
  word-break: break-all;
}

.trace-error {
  color: var(--color-danger-text) !important;
}

.trace-code {
  display: inline-block;
  margin-right: 6px;
  padding: 0 6px;
  border-radius: var(--radius-sm);
  background: var(--color-danger-light);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
}

.import-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
  white-space: normal;
}

.import-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  resize: vertical;
  outline: none;
}

.import-textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.import-hint,
.import-error {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
}

.import-hint {
  color: var(--color-text-weak);
}

.import-error {
  color: var(--color-danger-text);
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
