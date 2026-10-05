<script setup lang="ts">
import { useSessionStore } from '@shared/core'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createProductMaster,
  EXTERNAL,
  getProductMaster,
  updateProductMaster,
  type ProductMasterFields,
  type StoredObject,
} from '../api'
import ImageUrlList from '../components/ImageUrlList.vue'

const route = useRoute()
const router = useRouter()
const session = useSessionStore()

const productId = computed(() => (route.params.id ? Number(route.params.id) : null))
const createdBy = ref<number | null>(null)

const isOwner = computed(() => {
  if (productId.value === null) return true
  if (session.user?.superuser) return true
  return createdBy.value !== null && createdBy.value === session.user?.id
})

const editable = computed(() => isOwner.value)

const TEXT_FIELDS = [
  'asin',
  'color',
  'store',
  'pid',
  'category',
  'description',
  'selling_points',
] as const
const IMAGE_FIELDS = ['sub_images', 'three_view_images', 'three_view_reference_images'] as const

const form = reactive<ProductMasterFields>({
  sku: '',
  asin: null,
  color: null,
  store: null,
  pid: null,
  category: null,
  description: null,
  selling_points: null,
  main_image: null,
  sub_images: [],
  three_view_images: [],
  three_view_reference_images: [],
})
/** 主图用单元素列表编辑，复用 ImageUrlList */
const mainImages = ref<StoredObject[]>([])
const error = ref('')

/** 外部链接去掉首尾空白，空链接丢弃；存储对象原样保留 */
function cleanImages(images: StoredObject[]): StoredObject[] {
  return images
    .map((image) => (image.type === EXTERNAL ? { ...image, url: image.url?.trim() || null } : image))
    .filter((image) => image.type !== EXTERNAL || image.url)
}
const saving = ref(false)

onMounted(async () => {
  if (productId.value === null) return
  try {
    const data = await getProductMaster(productId.value)
    createdBy.value = data.created_by
    form.sku = data.sku
    for (const key of TEXT_FIELDS) form[key] = data[key]
    for (const key of IMAGE_FIELDS) form[key] = data[key]
    mainImages.value = data.main_image ? [data.main_image] : []
  } catch (e) {
    error.value = (e as Error).message
  }
})

async function submit(): Promise<void> {
  if (!editable.value) return
  saving.value = true
  try {
    const fields: ProductMasterFields = { ...form, sku: form.sku.trim() }
    for (const key of TEXT_FIELDS) fields[key] = form[key]?.trim() || null
    for (const key of IMAGE_FIELDS) fields[key] = cleanImages(form[key])
    fields.main_image = cleanImages(mainImages.value)[0] ?? null
    if (productId.value === null) {
      await createProductMaster(fields)
    } else {
      await updateProductMaster(productId.value, fields)
    }
    await router.push('/tiktok_studio/product-masters')
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
          <RouterLink to="/tiktok_studio/product-masters" class="breadcrumb-item">商品资产库</RouterLink>
          <span class="breadcrumb-separator">/</span>
          <span class="breadcrumb-current">{{ productId === null ? '新建商品' : (editable ? `编辑商品 #${productId}` : `查看商品 #${productId}`) }}</span>
        </div>
        <div class="title-with-badge">
          <h1>{{ productId === null ? '新建商品资产' : (editable ? `编辑商品 #${productId}` : `查看商品 #${productId}`) }}</h1>
          <span v-if="productId !== null && !editable" class="badge-readonly">只读浏览模式</span>
        </div>
        <p class="header-desc">
          {{ productId !== null && !editable ? '当前商品由其他成员创建，您处于只读查看模式，不可修改内容。' : '维护商品基础信息、卖点描述与主图、副图、三视图等素材资产。' }}
        </p>
      </div>

      <div class="header-actions">
        <RouterLink to="/tiktok_studio/product-masters" class="btn-secondary">
          返回列表
        </RouterLink>
        <button
          v-if="editable"
          form="product-form"
          type="submit"
          class="btn-primary"
          :disabled="saving"
        >
          {{ saving ? '正在保存...' : '保存商品' }}
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
    <form id="product-form" class="form-card" @submit.prevent="submit">
      <fieldset :disabled="!editable || saving" class="form-fieldset">
        <div class="form-grid">
          <div class="form-group inline">
            <label class="form-label required">产品货号</label>
            <div class="form-control-wrap">
              <input v-model="form.sku" required maxlength="64" class="form-control" />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label">ASIN</label>
            <div class="form-control-wrap">
              <input v-model="form.asin" maxlength="32" class="form-control" />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label">颜色</label>
            <div class="form-control-wrap">
              <input v-model="form.color" maxlength="64" class="form-control" />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label">销售店铺</label>
            <div class="form-control-wrap">
              <input v-model="form.store" maxlength="128" class="form-control" />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label">PID</label>
            <div class="form-control-wrap">
              <input v-model="form.pid" maxlength="64" class="form-control" />
            </div>
          </div>

          <div class="form-group inline">
            <label class="form-label">类目</label>
            <div class="form-control-wrap">
              <input v-model="form.category" maxlength="64" class="form-control" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">产品描述</label>
            <div class="form-control-wrap">
              <textarea v-model="form.description" rows="5" class="form-textarea" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">产品卖点</label>
            <div class="form-control-wrap">
              <textarea v-model="form.selling_points" rows="5" class="form-textarea" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">主图</label>
            <div class="form-control-wrap">
              <ImageUrlList v-model="mainImages" :max="1" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">副图</label>
            <div class="form-control-wrap">
              <ImageUrlList v-model="form.sub_images" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">三视图</label>
            <div class="form-control-wrap">
              <ImageUrlList v-model="form.three_view_images" :max="3" />
            </div>
          </div>

          <div class="form-group inline col-span-2 align-start">
            <label class="form-label">三视图参考图</label>
            <div class="form-control-wrap">
              <ImageUrlList v-model="form.three_view_reference_images" :max="3" />
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

.title-with-badge {
  display: flex;
  align-items: center;
  gap: 12px;
}

.title-with-badge h1,
.header-titles h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.badge-readonly {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--color-surface-subtle);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
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

.form-control:disabled,
.form-textarea:disabled {
  background: var(--color-surface-subtle);
  color: var(--color-text);
  -webkit-text-fill-color: var(--color-text);
  opacity: 0.88;
  cursor: default;
  border-color: var(--color-border);
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
