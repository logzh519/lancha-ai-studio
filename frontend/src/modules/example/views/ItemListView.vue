<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { createItem, listItems, type Item } from '../api'

const items = ref<Item[]>([])
const name = ref('')
const error = ref('')

async function refresh(): Promise<void> {
  try {
    items.value = await listItems()
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function submit(): Promise<void> {
  if (!name.value.trim()) return
  await createItem(name.value.trim())
  name.value = ''
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <section>
    <h1>条目列表</h1>
    <!-- v-permission 做按钮级控制：没有创建权限的用户看不到这块 -->
    <form v-permission="'example:item:create'" @submit.prevent="submit">
      <input v-model="name" placeholder="条目名称" />
      <button type="submit">新增</button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
    <ul>
      <li v-for="item in items" :key="item.id">{{ item.name }}</li>
    </ul>
  </section>
</template>

<style scoped>
form {
  display: flex;
  gap: var(--space-sm);
  margin: var(--space-md) 0;
}

input,
button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}

.error {
  color: #d03050;
}
</style>
