<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  deleteScriptTemplate,
  listScriptTemplates,
  type ScriptTemplateSummary,
} from '../api'

const PAGE_SIZE = 20

const templates = ref<ScriptTemplateSummary[]>([])
const total = ref(0)
const page = ref(1)
const error = ref('')
const keywordInput = ref('')
const keyword = ref('')
const jumpInput = ref(1)

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

function search(): Promise<void> {
  keyword.value = keywordInput.value.trim()
  return load(1)
}

function jump(): Promise<void> {
  const target = Math.min(pageCount.value, Math.max(1, Math.trunc(Number(jumpInput.value)) || 1))
  return load(target)
}

async function load(target: number): Promise<void> {
  try {
    const result = await listScriptTemplates(target, PAGE_SIZE, keyword.value)
    total.value = result.total
    const lastPage = Math.max(1, Math.ceil(result.total / PAGE_SIZE))
    if (target > lastPage) {
      await load(lastPage)
      return
    }
    templates.value = result.items
    page.value = target
    jumpInput.value = target
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function remove(template: ScriptTemplateSummary): Promise<void> {
  if (!window.confirm(`确定删除「${template.name}」？删除后不可恢复。`)) return
  try {
    await deleteScriptTemplate(template.id)
    await load(page.value)
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(() => load(1))
</script>

<template>
  <section class="page">
    <header>
      <h1>爆款脚本库</h1>
      <form class="search" @submit.prevent="search">
        <input v-model="keywordInput" type="search" maxlength="128" placeholder="按模板名称搜索" />
        <button type="submit">搜索</button>
      </form>
      <RouterLink v-permission="'tiktok:script_template:create'" to="/tiktok/script-templates/new" class="button">
        新建脚本
      </RouterLink>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="table-scroll">
      <table>
        <thead>
          <tr>
            <th>模板ID</th>
            <th>模板名称</th>
            <th>适合类目</th>
            <th>适合时长</th>
            <th>状态</th>
            <th>版本</th>
            <th>参考视频</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="template in templates" :key="template.id">
            <td>{{ template.id }}</td>
            <td>{{ template.name }}</td>
            <td>{{ CATEGORY_LABELS[template.category] }}</td>
            <td>{{ template.duration_seconds }} 秒</td>
            <td>{{ STATUS_LABELS[template.status] }}</td>
            <td>{{ template.version }}</td>
            <td>
              <a
                v-if="template.reference_video_url"
                :href="template.reference_video_url"
                target="_blank"
                rel="noopener"
              >
                查看
              </a>
            </td>
            <td>{{ new Date(template.updated_at).toLocaleString() }}</td>
            <td class="actions">
              <RouterLink :to="`/tiktok/script-templates/${template.id}`">查看/编辑</RouterLink>
              <button v-permission="'tiktok:script_template:delete'" type="button" @click="remove(template)">
                删除
              </button>
            </td>
          </tr>
          <tr v-if="!templates.length && !error">
            <td colspan="9" class="empty">{{ keyword ? '没有匹配的脚本' : '暂无脚本' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <footer class="pager">
      <span>共 {{ total }} 条</span>
      <button type="button" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
      <span>第 {{ page }} / {{ pageCount }} 页</span>
      <button type="button" :disabled="page >= pageCount" @click="load(page + 1)">下一页</button>
      <form class="jump" @submit.prevent="jump">
        跳至
        <input v-model.number="jumpInput" type="number" min="1" :max="pageCount" />
        页
        <button type="submit">跳转</button>
      </form>
    </footer>
  </section>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

header {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

h1 {
  margin: 0;
}

.search {
  display: flex;
  flex: 1;
  justify-content: flex-end;
  gap: var(--space-sm);
}

.search input {
  width: 240px;
}

.jump {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.jump input {
  width: 64px;
}

input {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font: inherit;
}

.table-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}

table {
  width: 100%;
  border-collapse: collapse;
}

th,
td {
  padding: var(--space-sm);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
  white-space: nowrap;
}

thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--color-bg);
}

.actions {
  display: flex;
  gap: var(--space-sm);
}

.pager {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-md);
  padding-top: var(--space-md);
  font-size: 14px;
}

.button,
button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  text-decoration: none;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.empty {
  color: var(--color-text-weak);
  text-align: center;
}

.error {
  flex-shrink: 0;
  color: #d03050;
}
</style>
