import { request } from '@shared/core'

export interface ReceivedItem {
  item_id: number
  name: string
}

export const listReceivedEvents = () => request<ReceivedItem[]>('/example_b/events')