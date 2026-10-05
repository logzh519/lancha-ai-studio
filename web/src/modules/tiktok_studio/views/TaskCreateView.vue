<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  createTaskBatch,
  listBatchTasks,
  listTaskBatches,
  previewTaskOrder,
  type BatchSummary,
  type BatchCreateResult,
  type TaskOrderPreviewItem,
  type TaskSummary,
} from '../api'

interface PreviewRow extends TaskOrderPreviewItem {
  rowKey: string
  selectable: boolean
}

const SKU_LIMIT = 50
const BATCH_LIMIT = 2000
const skuInput = ref('')
const batchName = ref('')
const note = ref('')
const rows = ref<PreviewRow[]>([])
const selectedKeys = ref(new Set<string>())
const previewing = ref(false)
const creating = ref(false)
const error = ref('')
const result = ref<BatchCreateResult | null>(null)
const requestFingerprint = ref('')
const requestId = ref('')
const batches = ref<BatchSummary[]>([])
const batchesTotal = ref(0)
const batchesLoading = ref(false)
const batchesError = ref('')
const expandedBatchId = ref<string | null>(null)
const batchTasks = ref<Record<string, { items: TaskSummary[]; total: number; page: number }>>({})
const loadingTasksFor = ref<string | null>(null)

const normalizedSkus = computed(() => [
  ...new Set(
    skuInput.value
      .split(/[;；,，\s]+/)
      .map((sku) => sku.trim().toUpperCase())
      .filter(Boolean),
  ),
])

const selectedRows = computed(() => rows.value.filter((row) => selectedKeys.value.has(row.rowKey)))
const selectableRows = computed(() => rows.value.filter((row) => row.selectable))
const allSelected = computed(
  () => selectableRows.value.length > 0 && selectableRows.value.every((row) => selectedKeys.value.has(row.rowKey)),
)

function setSelection(rowKey: string, checked: boolean): void {
  const next = new Set(selectedKeys.value)
  if (checked) next.add(rowKey)
  else next.delete(rowKey)
  selectedKeys.value = next
}

function toggleAll(): void {
  selectedKeys.value = allSelected.value
    ? new Set()
    : new Set(selectableRows.value.map((row) => row.rowKey))
}

function closePreview(): void {
  rows.value = []
  selectedKeys.value = new Set()
  requestFingerprint.value = ''
  requestId.value = ''
  error.value = ''
}

function makeRequestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function batchStatusLabel(status: string): string {
  return ({ running: '进行中', paused: '已暂停', completed: '已完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] ?? status
}

function taskStatusLabel(status: string): string {
  return ({ admitted_pending: '待准入', running: '处理中', awaiting_review: '待审核', completed: '已完成', failed: '失败', paused: '已暂停', cancelled: '已取消' } as Record<string, string>)[status] ?? status
}

async function loadBatches(expandId?: string): Promise<void> {
  batchesLoading.value = true
  batchesError.value = ''
  try {
    const response = await listTaskBatches()
    batches.value = response.items
    batchesTotal.value = response.total
    if (expandId && response.items.some((batch) => batch.id === expandId)) {
      expandedBatchId.value = expandId
      await loadBatchTasks(expandId)
    }
  } catch (caught) {
    batchesError.value = (caught as Error).message || '批次列表加载失败'
  } finally {
    batchesLoading.value = false
  }
}

async function loadBatchTasks(batchId: string, page = 1, append = false): Promise<void> {
  loadingTasksFor.value = batchId
  batchesError.value = ''
  try {
    const response = await listBatchTasks(batchId, page)
    const previous = batchTasks.value[batchId]
    batchTasks.value = {
      ...batchTasks.value,
      [batchId]: {
        items: append && previous ? [...previous.items, ...response.items] : response.items,
        total: response.total,
        page,
      },
    }
  } catch (caught) {
    batchesError.value = (caught as Error).message || '任务列表加载失败'
  } finally {
    loadingTasksFor.value = null
  }
}

async function toggleBatch(batchId: string): Promise<void> {
  if (expandedBatchId.value === batchId) {
    expandedBatchId.value = null
    return
  }
  expandedBatchId.value = batchId
  if (!batchTasks.value[batchId]) await loadBatchTasks(batchId)
}

onMounted(() => {
  void loadBatches()
})

async function preview(): Promise<void> {
  if (previewing.value || creating.value) return
  if (!normalizedSkus.value.length) {
    error.value = '请先输入产品货号'
    return
  }
  if (normalizedSkus.value.length > SKU_LIMIT) {
    error.value = `单次最多预览 ${SKU_LIMIT} 个货号`
    return
  }
  previewing.value = true
  error.value = ''
  result.value = null
  requestId.value = ''
  requestFingerprint.value = ''
  try {
    const response = await previewTaskOrder(normalizedSkus.value)
    const seenAsins = new Set<string>()
    rows.value = response.items.map((item, index) => {
      const duplicate = item.asin !== null && seenAsins.has(item.asin)
      if (item.asin) seenAsins.add(item.asin)
      return {
        ...item,
        rowKey: `${index}:${item.sku}:${item.asin ?? 'unmapped'}`,
        selectable: Boolean(item.asin) && !duplicate,
      }
    })
    selectedKeys.value = new Set(rows.value.filter((row) => row.selectable).map((row) => row.rowKey))
  } catch (caught) {
    error.value = (caught as Error).message || '货号预览失败，请重试'
    rows.value = []
    selectedKeys.value = new Set()
  } finally {
    previewing.value = false
  }
}

async function createBatch(): Promise<void> {
  if (creating.value) return
  if (!batchName.value.trim()) {
    error.value = '请填写批次名称'
    return
  }
  if (!selectedRows.value.length) {
    error.value = '请至少选择一个有效 ASIN'
    return
  }
  if (selectedRows.value.length > BATCH_LIMIT) {
    error.value = `单批最多创建 ${BATCH_LIMIT} 个任务，请拆分批次`
    return
  }

  const payloadItems = selectedRows.value.map(({ sku, asin, color, shop }) => ({
    sku,
    asin: asin as string,
    color,
    shop,
  }))
  const fingerprint = JSON.stringify({
    name: batchName.value.trim(),
    pipeline_key: 'video_gen_15s',
    items: payloadItems,
    note: note.value.trim() || null,
  })
  if (fingerprint !== requestFingerprint.value) {
    requestFingerprint.value = fingerprint
    requestId.value = makeRequestId()
  }

  creating.value = true
  error.value = ''
  try {
    result.value = await createTaskBatch({
      request_id: requestId.value,
      name: batchName.value.trim(),
      pipeline_key: 'video_gen_15s',
      items: payloadItems,
      note: note.value.trim() || null,
    })
    requestId.value = ''
    requestFingerprint.value = ''
    await loadBatches(result.value.id)
  } catch (caught) {
    error.value = (caught as Error).message || '创建批次失败，请重试'
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <main class="task-create-page">
    <header class="page-heading">
      <h1>任务建单</h1>
      <div class="pipeline-label header-count-badge">
        15 秒视频管线
      </div>
    </header>

    <section class="order-section" aria-labelledby="sku-heading">
      <div class="section-heading section-heading-inline">
        <h2 id="sku-heading">输入产品货号</h2>
        <p>支持空格、逗号或分号分隔，单次最多 {{ SKU_LIMIT }} 个货号</p>
      </div>
      <form class="sku-form" @submit.prevent="preview">
        <label class="sr-only" for="sku-input">产品货号</label>
        <input
          id="sku-input"
          class="sku-input"
          type="text"
          v-model="skuInput"
          placeholder="例如：WTK9167, WTK9168"
          :disabled="previewing || creating"
        />
        <button class="action-button btn-secondary preview-button" type="submit" :disabled="previewing || creating">
          <svg v-if="!previewing" viewBox="0 0 20 20" aria-hidden="true">
            <path d="M8.75 3.5a5.25 5.25 0 1 0 3.295 9.338l3.558 3.559 1.06-1.061-3.558-3.558A5.25 5.25 0 0 0 8.75 3.5Zm0 1.5a3.75 3.75 0 1 1 0 7.5 3.75 3.75 0 0 1 0-7.5Z" />
          </svg>
          <span>{{ previewing ? '展开中…' : '预览货号' }}</span>
        </button>
      </form>
    </section>

    <div v-if="error" class="message message-error" role="alert">
      <span class="message-mark">!</span>
      <span>{{ error }}</span>
      <button type="button" aria-label="关闭错误提示" @click="error = ''">×</button>
    </div>

    <div v-if="result" class="message message-success" role="status">
      <span class="message-mark">✓</span>
      <span>批次 {{ result.id }} 已创建，共 {{ result.total_tasks }} 个任务。</span>
    </div>

    <section v-if="rows.length" class="order-section preview-section" aria-labelledby="preview-heading">
      <div class="section-heading section-heading-row">
        <div class="section-heading-main">
          <div>
            <h2 id="preview-heading">确认商品映射</h2>
            <p>{{ selectedRows.length }} / {{ rows.length }} 个 ASIN 已选择</p>
          </div>
        </div>
        <div class="selection-actions">
          <button type="button" @click="toggleAll">{{ allSelected ? '取消全选' : '全选有效项' }}</button>
          <span class="action-divider"></span>
          <button type="button" @click="selectedKeys = new Set()">清空</button>
          <span class="action-divider"></span>
          <button class="dismiss-preview-button" type="button" title="关闭映射预览" @click="closePreview">
            <svg viewBox="0 0 20 20" aria-hidden="true">
              <path d="M5.47 4.41a.75.75 0 0 0-1.06 1.06L8.94 10l-4.53 4.53a.75.75 0 1 0 1.06 1.06L10 11.06l4.53 4.53a.75.75 0 0 0 1.06-1.06L11.06 10l4.53-4.53a.75.75 0 0 0-1.06-1.06L10 8.94 5.47 4.41Z" />
            </svg>
            <span>关闭预览</span>
          </button>
        </div>
      </div>

      <div class="table-frame">
        <table class="mapping-table">
          <thead>
            <tr>
              <th class="check-column">
                <input
                  type="checkbox"
                  aria-label="选择全部有效映射"
                  :checked="allSelected"
                  :disabled="!selectableRows.length || creating"
                  @change="toggleAll"
                />
              </th>
              <th>产品货号</th>
              <th>ASIN</th>
              <th>颜色</th>
              <th>销售店铺</th>
              <th>提示</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.rowKey" :class="{ 'row-unavailable': !row.selectable }">
              <td class="check-column">
                <input
                  type="checkbox"
                  :aria-label="`选择 ${row.asin || row.sku}`"
                  :checked="selectedKeys.has(row.rowKey)"
                  :disabled="!row.selectable || creating"
                  @change="setSelection(row.rowKey, ($event.target as HTMLInputElement).checked)"
                />
              </td>
              <td class="sku-cell">{{ row.sku }}</td>
              <td class="asin-cell">{{ row.asin || '未关联' }}</td>
              <td>{{ row.color || '—' }}</td>
              <td>{{ row.shop || '—' }}</td>
              <td>
                <span v-if="row.warnings.length" class="warning-text">{{ row.warnings.join('；') }}</span>
                <span v-else class="ready-text">可创建</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="batch-form">
        <div class="batch-fields">
          <label>
            <span>批次名称 <b>*</b></span>
            <input v-model="batchName" maxlength="255" placeholder="例如：秋季新品第一批" :disabled="creating" />
          </label>
          <label>
            <span>备注</span>
            <input v-model="note" placeholder="可选" :disabled="creating" />
          </label>
        </div>
        <div class="create-row">
          <span class="create-summary">将创建 {{ selectedRows.length }} 个视频任务</span>
          <button
            type="button"
            class="action-button btn-primary create-button"
            :disabled="creating || !selectedRows.length"
            @click="createBatch"
          >
            <svg v-if="!creating" viewBox="0 0 20 20" aria-hidden="true">
              <path d="M10 3a.75.75 0 0 1 .75.75v5.5h5.5a.75.75 0 0 1 0 1.5h-5.5v5.5a.75.75 0 0 1-1.5 0v-5.5h-5.5a.75.75 0 0 1 0-1.5h5.5v-5.5A.75.75 0 0 1 10 3Z" />
            </svg>
            <span>{{ creating ? '创建中…' : '确认创建批次' }}</span>
          </button>
        </div>
      </div>
    </section>

    <section class="order-section recent-batches" aria-labelledby="batches-heading">
      <div class="section-heading section-heading-row">
        <div class="section-heading-main">
          <div>
            <h2 id="batches-heading">我的批次</h2>
            <p>共 {{ batchesTotal }} 个批次，刷新后仍可查看</p>
          </div>
        </div>
        <button class="action-button btn-secondary refresh-button" type="button" :disabled="batchesLoading" @click="loadBatches(expandedBatchId ?? undefined)">
          {{ batchesLoading ? '刷新中…' : '刷新列表' }}
        </button>
      </div>

      <div v-if="batchesError" class="message message-error" role="alert">
        <span class="message-mark">!</span>
        <span>{{ batchesError }}</span>
      </div>
      <div v-if="batchesLoading && !batches.length" class="batch-empty">正在加载批次…</div>
      <div v-else-if="!batches.length" class="batch-empty">还没有创建过批次</div>
      <div v-else class="batch-list">
        <article v-for="batch in batches" :key="batch.id" class="batch-entry">
          <button
            class="batch-row"
            type="button"
            :aria-expanded="expandedBatchId === batch.id"
            @click="toggleBatch(batch.id)"
          >
            <span class="batch-expand" :class="{ expanded: expandedBatchId === batch.id }" aria-hidden="true">›</span>
            <span class="batch-main">
              <strong>{{ batch.name }}</strong>
              <small>{{ batch.id }}</small>
            </span>
            <span class="batch-count">{{ batch.total_tasks }} 个任务</span>
            <span class="batch-status">{{ batchStatusLabel(batch.status) }}</span>
            <time>{{ new Date(batch.created_at).toLocaleString() }}</time>
          </button>

          <div v-if="expandedBatchId === batch.id" class="batch-task-panel">
            <div v-if="loadingTasksFor === batch.id && !batchTasks[batch.id]" class="batch-empty">正在加载任务…</div>
            <div v-else-if="batchTasks[batch.id]?.items.length" class="task-table-wrap">
              <table class="task-table">
                <thead>
                  <tr><th>ASIN</th><th>货号</th><th>颜色</th><th>销售店铺</th><th>状态</th></tr>
                </thead>
                <tbody>
                  <tr v-for="task in batchTasks[batch.id].items" :key="task.id">
                    <td>{{ task.biz_key }}</td>
                    <td>{{ task.context.sku || '—' }}</td>
                    <td>{{ task.context.color || '—' }}</td>
                    <td>{{ task.context.shop || '—' }}</td>
                    <td><span class="task-status">{{ taskStatusLabel(task.status) }}</span></td>
                  </tr>
                </tbody>
              </table>
              <button
                v-if="batchTasks[batch.id].items.length < batchTasks[batch.id].total"
                class="action-button btn-secondary load-more-button"
                type="button"
                :disabled="loadingTasksFor === batch.id"
                @click="loadBatchTasks(batch.id, batchTasks[batch.id].page + 1, true)"
              >
                {{ loadingTasksFor === batch.id ? '加载中…' : `加载更多（${batchTasks[batch.id].items.length}/${batchTasks[batch.id].total}）` }}
              </button>
            </div>
            <div v-else class="batch-empty">该批次暂无任务</div>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.task-create-page {
  --ink: var(--color-text);
  --muted: var(--color-text-muted);
  --line: var(--color-border);
  --surface: var(--color-surface-subtle);
  --teal: var(--color-primary);
  --teal-dark: var(--color-primary-hover);
  --coral: var(--color-danger);
  max-width: 1180px;
  min-width: 0;
  width: 100%;
  box-sizing: border-box;
  margin: 0 auto;
  padding: 28px 32px 56px;
  color: var(--ink);
}

.page-heading,
.section-heading-row,
.section-heading-main,
.sku-form,
.create-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.page-heading {
  flex-shrink: 0;
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
}

h1,
h2,
p {
  margin-top: 0;
}

h1 {
  margin-bottom: 0;
  color: var(--color-text);
  font-size: 22px;
  font-weight: 700;
}

.header-count-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-full);
  padding: 3px 9px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.pipeline-label {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
}

.order-section {
  min-width: 0;
  padding: 26px 0 28px;
  border-bottom: 1px solid var(--line);
}

.recent-batches {
  border-bottom: 0;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 18px;
}

.section-heading-inline {
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 14px;
}

h2 {
  margin-bottom: 5px;
  color: var(--color-text);
  font-size: 16px;
  font-weight: 700;
}

.section-heading-inline h2,
.section-heading-inline p {
  margin-bottom: 0;
}

.section-heading p {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 13px;
}

.sku-form {
  align-items: center;
}

.sku-input,
.batch-fields input {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface-subtle);
  color: var(--ink);
  font: inherit;
  transition: all var(--transition-fast);
}

.sku-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 36px;
  padding: 0 12px;
  font-size: 13px;
}

.sku-input:focus,
.batch-fields input:focus {
  border-color: var(--color-primary);
  outline: none;
  background: var(--color-surface);
  box-shadow: 0 0 0 3px rgb(37 99 235 / 12%);
}

.action-button {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 0;
  border-radius: var(--radius);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.action-button.btn-primary {
  border: 0;
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 2px 6px rgb(37 99 235 / 25%);
}

.action-button.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.action-button.btn-secondary {
  border: 1px solid var(--color-primary-border);
  background: var(--color-primary-light);
  color: var(--color-primary);
}

.action-button.btn-secondary:hover:not(:disabled) {
  background: var(--color-surface);
}

.action-button:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.action-button svg {
  width: 18px;
  height: 18px;
  fill: currentColor;
}

.preview-button {
  flex: 0 0 auto;
}

.message {
  display: flex;
  align-items: center;
  gap: 11px;
  margin: 18px 0 0;
  padding: 12px 14px;
  border: 1px solid;
  border-radius: var(--radius);
  font-size: 13px;
}

.message-error {
  border-color: #fecaca;
  background: var(--color-danger-light);
  color: var(--color-danger-text);
}

.message-success {
  border-color: #bbf7d0;
  background: var(--color-success-light);
  color: var(--color-success-text);
}

.message-mark {
  font-weight: 800;
}

.message button {
  margin-left: auto;
  border: 0;
  background: none;
  color: inherit;
  font-size: 19px;
  cursor: pointer;
}

.section-heading-main {
  justify-content: flex-start;
  gap: 14px;
}

.section-heading-main .section-heading {
  margin-bottom: 0;
}

.selection-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.selection-actions button {
  border: 0;
  padding: 4px 0;
  background: none;
  color: var(--color-primary);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

.selection-actions .dismiss-preview-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--color-text-muted);
}

.selection-actions .dismiss-preview-button:hover {
  color: var(--color-danger-text);
}

.dismiss-preview-button svg {
  width: 15px;
  height: 15px;
  fill: currentColor;
}

.action-divider {
  width: 1px;
  height: 14px;
  background: var(--line);
}

.table-frame {
  overflow-x: auto;
}

.mapping-table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.mapping-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  height: 42px;
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}

.mapping-table td {
  height: 46px;
  border-top: 1px solid var(--color-border-subtle);
  vertical-align: middle;
}

.mapping-table tbody tr:hover td {
  background: var(--color-surface-hover);
}

.mapping-table th,
.mapping-table td {
  padding: 10px 16px;
  white-space: nowrap;
}

.check-column {
  width: 42px;
  text-align: center;
}

input[type='checkbox'] {
  width: 16px;
  height: 16px;
  accent-color: var(--color-primary);
  vertical-align: middle;
}

.row-unavailable {
  color: var(--color-text-weak);
  background: var(--color-surface-subtle);
}

.sku-cell,
.asin-cell {
  font-variant-numeric: tabular-nums;
}

.sku-cell {
  font-weight: 700;
}

.warning-text {
  color: var(--color-warning-text);
}

.ready-text {
  color: var(--color-success-text);
}

.batch-form {
  padding-top: 22px;
}

.batch-fields {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr);
  gap: 18px;
}

.batch-fields label {
  display: grid;
  gap: 7px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 650;
}

.batch-fields label b {
  color: var(--color-danger);
}

.batch-fields input {
  height: 40px;
  padding: 0 11px;
  font-size: 13px;
}

.create-row {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-subtle);
}

.create-summary {
  color: var(--muted);
  font-size: 13px;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  clip-path: inset(50%);
}

.refresh-button,
.load-more-button {
  flex: 0 0 auto;
  font-size: 12px;
}

.refresh-button:disabled,
.load-more-button:disabled {
  cursor: wait;
  opacity: 0.6;
}

.batch-list {
  overflow: hidden;
  border-top: 1px solid var(--color-border);
}

.batch-entry {
  border-bottom: 1px solid var(--color-border-subtle);
}

.batch-entry:last-child {
  border-bottom: 0;
}

.batch-row {
  display: grid;
  grid-template-columns: 22px minmax(140px, 1fr) 90px 84px minmax(145px, auto);
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 58px;
  border: 0;
  padding: 8px 12px;
  background: #fff;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}

.batch-row:hover {
  background: var(--color-surface-hover);
}

.batch-expand {
  color: var(--color-text-weak);
  font-size: 23px;
  line-height: 1;
  transform: rotate(0);
  transition: transform 120ms ease;
}

.batch-expand.expanded {
  transform: rotate(90deg);
}

.batch-main {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.batch-main strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.batch-main small,
.batch-row time {
  color: var(--color-text-weak);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.batch-count,
.batch-status {
  color: var(--color-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.batch-status {
  width: fit-content;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius-full);
  padding: 2px 8px;
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 11px;
}

.batch-task-panel {
  padding: 0 12px 14px 46px;
}

.task-table-wrap {
  overflow-x: auto;
}

.task-table {
  width: 100%;
  min-width: 560px;
  border-collapse: collapse;
  text-align: left;
  font-size: 13px;
}

.task-table th {
  height: 38px;
  color: var(--color-text-muted);
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}

.task-table td {
  height: 42px;
  border-top: 1px solid var(--color-border);
  vertical-align: middle;
}

.task-table tbody tr:hover td {
  background: var(--color-surface);
}

.task-status {
  display: inline-block;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  padding: 1px 8px;
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  font-size: 11px;
}

.load-more-button {
  margin-top: 10px;
}

.batch-empty {
  padding: 18px 12px;
  color: var(--color-text-weak);
  font-size: 13px;
}

@media (max-width: 700px) {
  :global(.workspace-body .module-sidebar) {
    display: none;
  }

  .task-create-page {
    padding: 20px 16px 40px;
  }

  .page-heading,
  .section-heading-row,
  .sku-form,
  .create-row {
    align-items: stretch;
    flex-direction: column;
  }

  .pipeline-label {
    align-self: flex-start;
  }

  .sku-input {
    width: 100%;
  }

  .preview-button {
    width: 100%;
  }

  .order-section {
    padding: 22px 0 24px;
  }

  .section-heading-row {
    gap: 12px;
  }

  .batch-fields {
    grid-template-columns: 1fr;
  }

  .create-button {
    width: 100%;
  }

  .batch-row {
    grid-template-columns: 18px minmax(0, 1fr) auto;
    gap: 8px;
  }

  .batch-row time {
    grid-column: 2 / 4;
  }

  .batch-task-panel {
    padding-left: 12px;
  }
}
</style>
