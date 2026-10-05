<script setup lang="ts">
const urls = defineModel<string[]>({ required: true })
const props = defineProps<{ max?: number }>()

function add(): void {
  if (props.max !== undefined && urls.value.length >= props.max) return
  urls.value = [...urls.value, '']
}

function update(index: number, value: string): void {
  urls.value = urls.value.map((url, i) => (i === index ? value : url))
}

function remove(index: number): void {
  urls.value = urls.value.filter((_, i) => i !== index)
}
</script>

<template>
  <div class="image-list">
    <div v-for="(url, index) in urls" :key="index" class="image-row">
      <a v-if="url" :href="url" target="_blank" rel="noopener" class="thumb">
        <img :src="url" alt="" />
      </a>
      <span v-else class="thumb thumb-empty" />
      <input
        :value="url"
        type="url"
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
      :disabled="max !== undefined && urls.length >= max"
      @click="add"
    >
      + 添加图片{{ max !== undefined ? `（${urls.length}/${max}）` : '' }}
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

.image-input:disabled {
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
