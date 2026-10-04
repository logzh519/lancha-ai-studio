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
  <section>
    <header>
      <div>
        <h1>Example B · 事件收件箱</h1>
        <p>进程内 · 同步派发</p>
      </div>
      <button type="button" @click="refresh">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="received.length === 0" class="empty">尚未收到条目事件</p>
    <ol v-else>
      <li v-for="(event, index) in received" :key="`${event.item_id}-${index}`">
        <span class="event-name">example_a.item_created</span>
        <span>#{{ event.item_id }} · {{ event.name }}</span>
      </li>
    </ol>
  </section>
</template>

<style scoped>
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-md);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--space-md);
}

h1 {
  margin: 0;
}

header p,
.empty {
  color: var(--color-muted);
}

button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  cursor: pointer;
}

ol {
  margin: 0;
  padding: 0;
  list-style: none;
}

li {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  padding: var(--space-md) 0;
  border-bottom: 1px solid var(--color-border);
}

.event-name {
  font-family: monospace;
  color: var(--color-muted);
}

.error {
  color: #d03050;
}
</style>