import { request } from '@shared/core'

export interface Account {
  id: number
  name: string
}

export const listAccounts = () => request<Account[]>('/tiktok/accounts')

export const createAccount = (name: string) =>
  request<Account>('/tiktok/accounts', { method: 'POST', body: JSON.stringify({ name }) })
