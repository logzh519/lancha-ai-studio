<script setup lang="ts">
import { confirmDialog } from '@shared/ui'
import { ref, shallowRef } from 'vue'

import { EXTERNAL, type StoredObject } from '../api'

const IMAGE_MAX_BYTES = 10 * 1024 * 1024
const IMAGE_ACCEPT = 'image/jpeg,image/png,image/webp,image/gif'

/**
 * 已有图片只能保留或移除；新增的占位卡片通过 upload 上传，未传 upload（商品尚未保存）时不能上传。
 * 传了 options 时图片只能从中选择，每张卡片都可以编辑改选，不支持上传。
 */
const images = defineModel<StoredObject[]>({ required: true })
const props = withDefaults(
  defineProps<{
    max?: number
    imageHeight?: number
    upload?: (file: File) => Promise<StoredObject>
    options?: StoredObject[]
    regenerate?: () => void
  }>(),
  { max: undefined, imageHeight: 230 },
)

const fileInput = ref<HTMLInputElement | null>(null)
const pickTarget = shallowRef<StoredObject | null>(null)
const uploadingTarget = shallowRef<StoredObject | null>(null)
const selectingTarget = shallowRef<StoredObject | null>(null)
const uploadError = ref('')

function toggleSelect(image: StoredObject): void {
  selectingTarget.value = selectingTarget.value === image ? null : image
}

function select(option: StoredObject): void {
  const target = selectingTarget.value
  images.value = images.value.map((image) => (image === target ? { ...option } : image))
  selectingTarget.value = null
}

function add(): void {
  if (props.max !== undefined && images.value.length >= props.max) return
  images.value = [...images.value, { key: null, url: '', type: EXTERNAL }]
}

function pick(image: StoredObject): void {
  pickTarget.value = image
  fileInput.value?.click()
}

async function onFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  const target = pickTarget.value
  if (!file || !target || !props.upload) return
  if (file.size > IMAGE_MAX_BYTES) {
    uploadError.value = '图片不能超过 10MB'
    return
  }
  uploadError.value = ''
  uploadingTarget.value = target
  try {
    const uploaded = await props.upload(file)
    images.value = images.value.map((image) => (image === target ? uploaded : image))
  } catch (e) {
    uploadError.value = (e as Error).message
  } finally {
    uploadingTarget.value = null
  }
}

function showDetail(image: StoredObject): void {
  void confirmDialog({
    title: '图片详情',
    message: `type：${image.type}\nkey：${image.key ?? '—'}\nurl：${image.url || '—'}`,
    type: 'info',
    confirmText: '关闭',
    showCancel: false,
  })
}

async function remove(index: number): Promise<void> {
  const confirmed = await confirmDialog({
    title: '确认移除图片',
    message: '确定移除这张图片？保存商品后生效。',
    type: 'danger',
    confirmText: '确定移除',
    cancelText: '取消',
  })
  if (!confirmed) return
  if (selectingTarget.value === images.value[index]) selectingTarget.value = null
  images.value = images.value.filter((_, i) => i !== index)
}
</script>

<template>
  <div class="image-list" :style="{ '--image-height': `${imageHeight}px` }">
    <div v-for="(image, index) in images" :key="index" class="image-card">
      <a v-if="image.url" :href="image.url" target="_blank" rel="noopener" class="image-box">
        <img :src="image.url" alt="" />
      </a>
      <div v-else-if="options" class="image-box image-empty">未选择图片</div>
      <div v-else class="image-box image-empty">
        {{ uploadingTarget === image ? '正在上传...' : (upload ? '未上传图片' : '保存商品后可上传') }}
      </div>

      <div class="card-footer">
        <a v-if="image.url || image.key" href="#" class="link-detail" @click.prevent="showDetail(image)">详情</a>
        <button
          v-if="regenerate && (image.url || image.key)"
          type="button"
          class="btn-link"
          @click="regenerate()"
        >
          重新生成
        </button>
        <button
          v-if="options"
          type="button"
          class="btn-link"
          @click="toggleSelect(image)"
        >
          {{ selectingTarget === image ? '收起' : '编辑' }}
        </button>
        <button
          v-else-if="!image.url && !image.key"
          type="button"
          class="btn-link"
          :disabled="!upload || uploadingTarget !== null"
          @click="pick(image)"
        >
          {{ uploadingTarget === image ? '上传中...' : '上传' }}
        </button>
        <button
          type="button"
          class="btn-link danger"
          :disabled="uploadingTarget === image"
          @click="remove(index)"
        >
          移除
        </button>
      </div>
    </div>

    <button
      type="button"
      class="image-card btn-add"
      :disabled="max !== undefined && images.length >= max"
      @click="add"
    >
      <span class="add-plus">+</span>
      <span>添加图片{{ max !== undefined ? `（${images.length}/${max}）` : '' }}</span>
    </button>

    <input ref="fileInput" type="file" :accept="IMAGE_ACCEPT" hidden @change="onFileChange" />
  </div>
  <div v-if="options && selectingTarget" class="option-panel">
    <span class="option-title">从主图 / 副图中选择：</span>
    <div v-if="options.length" class="option-list">
      <button
        v-for="(option, index) in options"
        :key="index"
        type="button"
        class="option-item"
        :class="{ active: option.url === selectingTarget.url }"
        :title="option.url ?? ''"
        @click="select(option)"
      >
        <img :src="option.url ?? ''" alt="" />
      </button>
    </div>
    <span v-else class="option-empty">暂无可选的主图或副图，请先上传</span>
  </div>
  <p v-if="uploadError" class="upload-error">{{ uploadError }}</p>
</template>

<style scoped>
.image-list {
  --card-width: 180px;
  --footer-height: 36px;
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 6px;
}

.image-card {
  flex: 0 0 var(--card-width);
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  overflow: hidden;
}

.image-box {
  display: flex;
  align-items: center;
  justify-content: center;
  height: var(--image-height);
  background: #ffffff;
  border-bottom: 1px solid var(--color-border);
}

.image-box img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.image-empty {
  background: var(--color-surface-subtle);
  color: var(--color-text-weak);
  font-size: 12px;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
  height: var(--footer-height);
  padding: 0 6px 0 10px;
}

.link-detail {
  margin-right: auto;
  color: var(--color-text-muted);
  font-size: 12px;
  text-decoration: none;
}

.link-detail:hover {
  color: var(--color-primary);
}

.btn-link {
  flex-shrink: 0;
  padding: 4px 6px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.btn-link.danger {
  color: var(--color-danger);
}
.btn-link:disabled {
  color: var(--color-text-weak);
  cursor: not-allowed;
}

fieldset:disabled .btn-link {
  display: none;
}

.option-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid var(--color-primary-border);
  border-radius: var(--radius);
  background: var(--color-primary-light);
}

.option-title,
.option-empty {
  color: var(--color-text-muted);
  font-size: 12px;
}

.option-list {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.option-item {
  flex: 0 0 72px;
  height: 92px;
  padding: 0;
  border: 2px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: #ffffff;
  overflow: hidden;
  cursor: pointer;
}

.option-item:hover,
.option-item.active {
  border-color: var(--color-primary);
}

.option-item img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.upload-error {
  margin: 4px 0 0;
  color: var(--color-danger-text);
  font-size: 12px;
}

.btn-add {
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: calc(var(--image-height) + var(--footer-height) + 3px);
  border-style: dashed;
  background: var(--color-surface-subtle);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.btn-add:hover:not(:disabled) {
  border-color: var(--color-primary);
}

.add-plus {
  font-size: 28px;
  line-height: 1;
}

.btn-add:disabled {
  color: var(--color-text-weak);
  cursor: not-allowed;
}

fieldset:disabled .btn-add {
  display: none;
}
</style>
