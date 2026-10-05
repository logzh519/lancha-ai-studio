<script setup lang="ts">
import { EXTERNAL, type StoredObject } from '../api'

/** 对象存储里的图片只能保留或移除；手工添加的是外部链接，可编辑 */
const images = defineModel<StoredObject[]>({ required: true })
const props = defineProps<{ max?: number }>()

function add(): void {
  if (props.max !== undefined && images.value.length >= props.max) return
  images.value = [...images.value, { key: null, url: '', type: EXTERNAL }]
}

function update(index: number, value: string): void {
  images.value = images.value.map((image, i) => (i === index ? { key: null, url: value, type: EXTERNAL } : image))
}

function remove(index: number): void {
  images.value = images.value.filter((_, i) => i !== index)
}
</script>

<template>
  <div class="image-list">
    <div v-for="(image, index) in images" :key="index" class="image-row">
      <a v-if="image.url" :href="image.url" target="_blank" rel="noopener" class="thumb">
        <img :src="image.url" alt="" />
      </a>
      <span v-else class="thumb thumb-empty" />
      <input
        :value="image.url ?? image.key"
        :type="image.type === EXTERNAL ? 'url' : 'text'"
        :readonly="image.type !== EXTERNAL"
        :title="image.type !== EXTERNAL ? `${image.type}: ${image.key}` : ''"
        required
        maxlength="2048"
        placeholder="https://..."
        class="image-input"
        @input="update(index, ($event.target as HTMLInputElement).value)"
      />
      <button type="button" class="btn-remove" @click="remove(index)">移除</button>
    </div>
    <button
      type="button"
      class="btn-add"
      :disabled="max !== undefined && images.length >= max"
      @click="add"
    >
      + 添加图片{{ max !== undefined ? `（${images.length}/${max}）` : '' }}
    </button>
  </div>
</template>

<style scoped>
.image-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.image-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.thumb {
  flex-shrink: 0;
  width: 38px;
  height: 38px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-surface-subtle);
  overflow: hidden;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-input {
  flex: 1;
  min-width: 0;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  outline: none;
}

.image-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.image-input:disabled,
.image-input:read-only {
  background: var(--color-surface-subtle);
}

.btn-remove,
.btn-add {
  border: none;
  background: transparent;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
}

.btn-remove {
  flex-shrink: 0;
  padding: 4px 8px;
  color: var(--color-danger);
}

.btn-add {
  align-self: flex-start;
  padding: 4px 0;
  color: var(--color-primary);
}

.btn-remove:disabled,
.btn-add:disabled {
  color: var(--color-text-weak);
  cursor: not-allowed;
}
</style>
