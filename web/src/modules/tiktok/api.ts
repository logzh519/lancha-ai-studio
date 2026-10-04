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

const BASE = '/tiktok/script-templates'

export const listScriptTemplates = () => request<ScriptTemplateSummary[]>(BASE)

export const getScriptTemplate = (id: number) => request<ScriptTemplate>(`${BASE}/${id}`)

export const createScriptTemplate = (fields: ScriptTemplateFields) =>
  request<ScriptTemplate>(BASE, { method: 'POST', body: JSON.stringify(fields) })

export const updateScriptTemplate = (id: number, fields: ScriptTemplateFields) =>
  request<ScriptTemplate>(`${BASE}/${id}`, { method: 'PUT', body: JSON.stringify(fields) })

export const deleteScriptTemplate = (id: number) => request<void>(`${BASE}/${id}`, { method: 'DELETE' })
