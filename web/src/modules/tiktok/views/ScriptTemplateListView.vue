<script setup lang="ts">
import { onMounted, ref } from 'vue'

import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  deleteScriptTemplate,
  listScriptTemplates,
  type ScriptTemplateSummary,
} from '../api'

const templates = ref<ScriptTemplateSummary[]>([])
const error = ref('')

async function refresh(): Promise<void> {
  try {
    templates.value = await listScriptTemplates()
    error.value = ''
  } catch (e) {
    error.value = (e as Error).message
  }
}

async function remove(template: ScriptTemplateSummary): Promise<void> {
  if (!window.confirm(`确定删除「${template.name}」？删除后不可恢复。`)) return
  try {
    await deleteScriptTemplate(template.id)
    await refresh()
  } catch (e) {
    error.value = (e as Error).message
  }
}

onMounted(refresh)
</script>

<template>
  <section>
    <header>
      <h1>爆款脚本库</h1>
      <RouterLink v-permission="'tiktok:script_template:create'" to="/tiktok/script-templates/new" class="button">
        新建脚本
      </RouterLink>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
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
            <a v-if="template.reference_video_url" :href="template.reference_video_url" target="_blank" rel="noopener">
              查看
            </a>
          </td>
          <td>{{ new Date(template.updated_at).toLocaleString() }}</td>
          <td class="actions">
            <RouterLink :to="`/tiktok/script-templates/${template.id}`">查看/编辑</RouterLink>
            <button v-permission="'tiktok:script_template:delete'" type="button" @click="remove(template)">删除</button>
          </td>
        </tr>
        <tr v-if="!templates.length && !error">
          <td colspan="9" class="empty">暂无脚本</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-md);
}

table {
  width: 100%;
  border-collapse: collapse;
  background: var(--color-surface);
}

th,
td {
  padding: var(--space-sm);
  border-bottom: 1px solid var(--color-border);
  text-align: left;
}

.actions {
  display: flex;
  gap: var(--space-sm);
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

.empty {
  color: var(--color-text-weak);
  text-align: center;
}

.error {
  color: #d03050;
}
</style>
