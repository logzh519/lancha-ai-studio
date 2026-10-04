<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { createAccount, listAccounts, type Account } from '../api'

const accounts = ref<Account[]>([])
const name = ref('')
const error = ref('')

async function refresh(): Promise<void> {
  try {
    accounts.value = await listAccounts()
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function submit(): Promise<void> {
  if (!name.value.trim()) return
  await createAccount(name.value.trim())
  name.value = ''
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <section>
    <h1>TikTok · 账号</h1>
    <form v-permission="'tiktok:account:create'" @submit.prevent="submit">
      <input v-model="name" placeholder="账号名称" />
      <button type="submit">新增</button>
    </form>
    <p v-if="error" class="error">{{ error }}</p>
    <ul>
      <li v-for="account in accounts" :key="account.id">{{ account.name }}</li>
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
