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
  <div class="form-container">
    <!-- 面包屑与页头 -->
    <div class="form-header">
      <div class="header-titles">
        <div class="breadcrumb">
          <RouterLink to="/" class="breadcrumb-item">应用广场</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <RouterLink to="/tiktok/script-templates" class="breadcrumb-item">爆款视频脚本库</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">{{ templateId === null ? '新建脚本模版' : `脚本 #${templateId}` }}</span>
        </div>
        <h1>{{ templateId === null ? '新建爆款脚本' : `编辑脚本 #${templateId}` }}</h1>
        <p class="header-desc">
          标准化组织短视频核心钩子（Hook）、爆点反转、文案台词与分镜提示，沉淀爆款生产资产。
        </p>
      </div>

      <div class="header-actions">
        <RouterLink to="/tiktok/script-templates" class="btn-secondary">
          返回列表
        </RouterLink>
        <button
          v-if="editable"
          form="template-form"
          type="submit"
          class="btn-primary"
          :disabled="saving"
        >
          {{ saving ? '正在保存...' : '保存模版' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      <svg viewBox="0 0 20 20" fill="currentColor" class="error-icon">
        <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clip-rule="evenodd" />
      </svg>
      <span>{{ error }}</span>
    </div>

    <!-- 表单卡片 -->
    <form id="template-form" class="form-card" @submit.prevent="submit">
      <fieldset :disabled="!editable || saving" class="form-fieldset">
        <div class="form-grid">
          <div class="form-group inline col-span-2">
            <label class="form-label required">模版名称</label>
            <div class="form-control-wrap">
              <input
                v-model="form.name"
                required
                maxlength="128"
                placeholder="例如：TikTok 痛点钩子+反转好物推荐"
                class="form-control"
              />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label required">适合类目</label>
            <div class="form-control-wrap">
              <select v-model="form.category" class="form-control">
                <option v-for="(label, value) in CATEGORY_LABELS" :key="value" :value="value">{{ label }}</option>
              </select>
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label required">适合时长（秒）</label>
            <div class="form-control-wrap">
              <input
                v-model.number="form.duration_seconds"
                type="number"
                min="1"
                required
                class="form-control"
              />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label required">上线状态</label>
            <div class="form-control-wrap">
              <select v-model="form.status" class="form-control">
                <option v-for="(label, value) in STATUS_LABELS" :key="value" :value="value">{{ label }}</option>
              </select>
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label required">版本号</label>
            <div class="form-control-wrap">
              <input
                v-model="form.version"
                required
                pattern="\d+\.\d+\.\d+"
                placeholder="1.0.0"
                class="form-control"
              />
            </div>
          </div>

          <div class="form-group inline col-span-2">
            <label class="form-label">参考视频</label>
            <div class="form-control-wrap">
              <input
                v-model="form.reference_video_url"
                type="url"
                maxlength="2048"
                placeholder="https://www.tiktok.com/@creator/video/..."
                class="form-control"
              />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label required">脚本内容</label>
            <div class="form-control-wrap">
              <textarea
                v-model="form.content"
                required
                rows="18"
                placeholder="请输入短视频分镜脚本内容，支持 Markdown 或分段台词规范..."
                class="form-textarea"
              />
            </div>
          </div>
        </div>
      </fieldset>
    </form>
  </div>
</template>

<style scoped>
.form-container {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  width: 100%;
}

/* 页头 */
.form-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--space-md);
  padding: 20px 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}

.header-titles {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.breadcrumb-item {
  color: var(--color-text-weak);
  transition: color var(--transition-fast);
}

.breadcrumb-item:hover {
  color: var(--color-primary);
}

.breadcrumb-separator {
  color: var(--color-border-hover);
}

.breadcrumb-current {
  color: var(--color-text-muted);
  font-weight: 500;
}

.header-titles h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.header-desc {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
  max-width: 680px;
  line-height: 1.5;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 按钮通用 */
.btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 18px;
  background: var(--color-primary);
  color: #ffffff;
  border: none;
  border-radius: var(--radius);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(37, 99, 235, 0.25);
  transition: all var(--transition-fast);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text-muted);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
  transition: all var(--transition-fast);
}

.btn-secondary:hover {
  background: var(--color-surface-subtle);
  color: var(--color-text);
  border-color: var(--color-border-hover);
}

/* 错误条目 */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-danger-light);
  border: 1px solid #fecaca;
  border-radius: var(--radius);
  color: var(--color-danger-text);
  font-size: 13px;
}

.error-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
}

/* 表单卡片 */
.form-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
  padding: 28px 32px;
}

.form-fieldset {
  display: flex;
  flex-direction: column;
  gap: 28px;
  margin: 0;
  padding: 0;
  border: none;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px 24px;
}

.col-span-2 {
  grid-column: span 2;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-group.inline {
  flex-direction: row;
  align-items: center;
  gap: 14px;
}

.form-group.inline.align-start {
  align-items: flex-start;
}

.form-group.inline .form-label {
  width: 120px;
  flex-shrink: 0;
  margin: 0;
  text-align: left;
}

.form-group.inline.align-start .form-label {
  padding-top: 10px;
}

.form-control-wrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  gap: 4px;
}

.form-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text);
}

.form-label.required::after {
  content: ' *';
  color: var(--color-danger);
}

.form-control {
  width: 100%;
  height: 38px;
  padding: 0 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  outline: none;
  transition: all var(--transition-fast);
}

.form-control:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.form-textarea {
  width: 100%;
  padding: 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  background: var(--color-surface);
  color: var(--color-text);
  font-size: 13px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  line-height: 1.6;
  outline: none;
  resize: vertical;
  transition: all var(--transition-fast);
}

.form-textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
  .col-span-2 {
    grid-column: span 1;
  }
  .form-group.inline {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }
  .form-group.inline .form-label {
    width: auto;
    text-align: left;
  }
  .form-group.inline.align-start .form-label {
    padding-top: 0;
  }
}
</style>
