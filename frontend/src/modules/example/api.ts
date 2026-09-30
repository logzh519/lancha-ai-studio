import { request } from '@shared/core'

export interface Item {
  id: number
  name: string
}

export const listItems = () => request<Item[]>('/example/items')

export const createItem = (name: string) =>
  request<Item>('/example/items', { method: 'POST', body: JSON.stringify({ name }) })
