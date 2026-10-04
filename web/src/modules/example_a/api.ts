import { request } from '@shared/core'

export interface Item {
  id: number
  name: string
}

export const listItems = () => request<Item[]>('/example_a/items')

export const createItem = (name: string) =>
  request<Item>('/example_a/items', { method: 'POST', body: JSON.stringify({ name }) })
