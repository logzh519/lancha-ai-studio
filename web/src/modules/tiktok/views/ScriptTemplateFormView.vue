<script setup lang="ts">
import { usePlatformStore } from '@shared/core'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  CATEGORY_LABELS,
  STATUS_LABELS,
  createScriptTemplate,
  getScriptTemplate,
  updateScriptTemplate,
  type ScriptTemplateFields,
} from '../api'

const route = useRoute()
const router = useRouter()
const platform = usePlatformStore()

const templateId = computed(() => (route.params.id ? Number(route.params.id) : null))
const editable = computed(() =>
  platform.has(templateId.value === null ? 'tiktok:script_template:create' : 'tiktok:script_template:update'),
)

const form = reactive<ScriptTemplateFields>({
  name: '',
  category: 'all',
  duration_seconds: 15,
  content: '',
  status: 'test',
  version: '1.0.0',
  reference_video_url: null,
})
const error = ref('')
const saving = ref(false)

onMounted(async () => {
  if (templateId.value === null) return
  try {
    const { name, category, duration_seconds, content, status, version, reference_video_url } =
      await getScriptTemplate(templateId.value)
    Object.assign(form, { name, category, duration_seconds, content, status, version, reference_video_url })
  } catch (e) {
    error.value = (e as Error).message
  }
})

async function submit(): Promise<void> {
  saving.value = true
  try {
    const fields = { ...form, reference_video_url: form.reference_video_url?.trim() || null }
    if (templateId.value === null) {
      await createScriptTemplate(fields)
    } else {
      await updateScriptTemplate(templateId.value, fields)
    }
    await router.push('/tiktok/script-templates')
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="page">
    <h1>{{ templateId === null ? '新建脚本' : `脚本 #${templateId}` }}</h1>
    <form @submit.prevent="submit">
      <div class="form-scroll">
        <fieldset :disabled="!editable || saving">
          <label class="inline">
            <span>模板名称</span>
            <input v-model="form.name" required maxlength="128" />
          </label>
          <div class="row">
            <label class="inline">
              <span>适合类目</span>
              <select v-model="form.category">
                <option v-for="(label, value) in CATEGORY_LABELS" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>
            <label class="inline">
              <span>适合时长（秒）</span>
              <input v-model.number="form.duration_seconds" type="number" min="1" required />
            </label>
            <label class="inline">
              <span>状态</span>
              <select v-model="form.status">
                <option v-for="(label, value) in STATUS_LABELS" :key="value" :value="value">{{ label }}</option>
              </select>
            </label>
            <label class="inline">
              <span>版本</span>
              <input v-model="form.version" required pattern="\d+\.\d+\.\d+" title="格式为 x.y.z，如 1.0.0" />
            </label>
          </div>
          <label class="inline">
            <span>参考视频</span>
            <input v-model="form.reference_video_url" type="url" maxlength="2048" placeholder="https://" />
          </label>
          <label>
            脚本内容
            <textarea v-model="form.content" required rows="24" />
          </label>
        </fieldset>
      </div>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions">
        <button v-if="editable" type="submit" :disabled="saving">保存</button>
        <RouterLink to="/tiktok/script-templates">返回列表</RouterLink>
      </div>
    </form>
  </section>
</template>

<style scoped>
.page,
form {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.page {
  height: 100%;
}

h1 {
  flex-shrink: 0;
  margin: 0 0 var(--space-md);
}

form {
  flex: 1;
}

.form-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
}

fieldset {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin: 0;
  padding: 0;
  border: none;
  min-width: 0;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.row {
  display: flex;
  gap: var(--space-md);
}

.row label {
  flex: 1;
}

label.inline {
  flex-direction: row;
  align-items: center;
  gap: var(--space-sm);
}

label.inline span {
  flex-shrink: 0;
  white-space: nowrap;
}

label.inline input,
label.inline select {
  flex: 1;
  min-width: 0;
}

input,
select,
textarea,
button {
  padding: 6px var(--space-sm);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  font: inherit;
}

textarea {
  font-family: ui-monospace, monospace;
  resize: vertical;
}

.actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.error {
  flex-shrink: 0;
  color: #d03050;
}
</style>
