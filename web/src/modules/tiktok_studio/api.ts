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
  main_image_url: string | null
  sub_images: string[]
  three_view_images: string[]
  three_view_reference_images: string[]
}

export type ProductMasterSummary = Pick<
  ProductMasterFields,
  'sku' | 'asin' | 'color' | 'store' | 'pid' | 'category' | 'main_image_url'
> & {
  id: number
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
