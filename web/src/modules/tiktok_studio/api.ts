import { request } from '@shared/core'

export type Category = 'all' | 'top' | 'bottom'
export type Status = 'formal' | 'test'

export const CATEGORY_LABELS: Record<Category, string> = { all: '全品类', top: '上衣', bottom: '下衣' }
export const STATUS_LABELS: Record<Status, string> = { formal: '正式', test: '测试' }

export interface ScriptTemplateFields {
  name: string
  category: Category
  duration_seconds: number
  content: string
  status: Status
  version: string
  reference_video_url: string | null
}

export interface ScriptTemplateSummary extends Omit<ScriptTemplateFields, 'content'> {
  id: number
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface ScriptTemplate extends ScriptTemplateSummary {
  content: string
}

export interface ScriptTemplatePage {
  items: ScriptTemplateSummary[]
  total: number
}

const BASE = '/tiktok_studio/script-templates'

export const listScriptTemplates = (page: number, pageSize: number, keyword = '') => {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (keyword) query.set('keyword', keyword)
  return request<ScriptTemplatePage>(`${BASE}?${query}`)
}

export const getScriptTemplate = (id: number) => request<ScriptTemplate>(`${BASE}/${id}`)

export const createScriptTemplate = (fields: ScriptTemplateFields) =>
  request<ScriptTemplate>(BASE, { method: 'POST', body: JSON.stringify(fields) })

export const updateScriptTemplate = (id: number, fields: ScriptTemplateFields) =>
  request<ScriptTemplate>(`${BASE}/${id}`, { method: 'PUT', body: JSON.stringify(fields) })

export const deleteScriptTemplate = (id: number) => request<void>(`${BASE}/${id}`, { method: 'DELETE' })

export interface ProductMasterFields {
  sku: string
  asin: string | null
  color: string | null
  store: string | null
  pid: string | null
  category: string | null
  description: string | null
  selling_points: string | null
  main_image: StoredObject | null
  sub_images: StoredObject[]
  three_view_images: StoredObject[]
  three_view_reference_images: StoredObject[]
}

/** 外部链接：没有对象存储 key，删除商品时不清理 */
export const EXTERNAL = 'external'

/** 图片资源；type 为存储类型（tos / obs）时 key 指向对象存储 */
export interface StoredObject {
  key: string | null
  url: string | null
  type: string
}

export type ImportStatus = 'pending' | 'running' | 'done' | 'failed'

export const IMPORT_STATUS_LABELS: Record<ImportStatus, string> = {
  pending: '等待',
  running: '进行中',
  done: '完成',
  failed: '失败',
}

export type ImportStage = 'crawl' | 'view' | 'gen'

/** 导入阶段失败的现场；该阶段成功后移除 */
export interface StageTrace {
  input: Record<string, unknown>
  output: Record<string, unknown>
  error_code: string | null
  error_message: string
}

export type ProductMasterSummary = Pick<
  ProductMasterFields,
  'sku' | 'asin' | 'color' | 'store' | 'pid' | 'category' | 'main_image'
> & {
  id: number
  crawl_status: ImportStatus | null
  crawl_error: string | null
  view_status: ImportStatus | null
  view_error: string | null
  gen_status: ImportStatus | null
  gen_error: string | null
  import_trace: Partial<Record<ImportStage, StageTrace>>
  created_by: number | null
  created_at: string
  updated_at: string
}

export type ProductMaster = ProductMasterSummary & ProductMasterFields

export interface ProductMasterPage {
  items: ProductMasterSummary[]
  total: number
}

const PRODUCT_BASE = '/tiktok_studio/product-masters'

export const listProductMasters = (page: number, pageSize: number, keyword = '') => {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (keyword) query.set('keyword', keyword)
  return request<ProductMasterPage>(`${PRODUCT_BASE}?${query}`)
}

export const getProductMaster = (id: number) => request<ProductMaster>(`${PRODUCT_BASE}/${id}`)

export const createProductMaster = (fields: ProductMasterFields) =>
  request<ProductMaster>(PRODUCT_BASE, { method: 'POST', body: JSON.stringify(fields) })

export const updateProductMaster = (id: number, fields: ProductMasterFields) =>
  request<ProductMaster>(`${PRODUCT_BASE}/${id}`, { method: 'PUT', body: JSON.stringify(fields) })

export const deleteProductMaster = (id: number) => request<void>(`${PRODUCT_BASE}/${id}`, { method: 'DELETE' })

/** 由后台按当前参考图重新生成三视图，进度体现在导入状态的生成阶段 */
export const regenerateThreeView = (id: number) =>
  request<ProductMaster>(`${PRODUCT_BASE}/${id}/regenerate-three-view`, { method: 'POST' })

/** 三视图参考图只能选自主图副图，不能上传 */
export type ProductImageField = 'main_image' | 'sub_images' | 'three_view_images'

/** 上传后立即写入商品对应字段：主图替换，其余字段追加 */
export const uploadProductImage = (id: number, field: ProductImageField, file: File) =>
  request<StoredObject>(`${PRODUCT_BASE}/${id}/images/${field}`, {
    method: 'POST',
    body: file,
    headers: { 'Content-Type': file.type },
  })

export interface ProductImportResult {
  created: ProductMasterSummary[]
  skipped: number
  failed: { sku: string; message: string }[]
}

export const importProductMasters = (skus: string[]) =>
  request<ProductImportResult>(`${PRODUCT_BASE}/import`, { method: 'POST', body: JSON.stringify({ skus }) })

export const retryProductImport = (id: number) =>
  request<ProductMaster>(`${PRODUCT_BASE}/${id}/retry-import`, { method: 'POST' })
