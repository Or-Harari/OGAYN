import { create } from 'zustand'
import { api } from '@/lib/api'

export interface BotInfo {
  id: number
  name: string
  userdir: string
  status: string
  mode?: string | null
  pid?: number | null
  config_path?: string | null
  strategy?: Record<string, any> | null
}

export interface TradeRow {
  id: string
  bot_id: number
  mode?: string
  pair: string
  side: string
  open_rate: number
  close_rate?: number
  profit_abs?: number
  profit_ratio?: number
  open_date?: string
  close_date?: string
  status?: string
}

interface DataState {
  bots: BotInfo[]
  tradesByBot: Record<number, TradeRow[]>
  setBots: (bots: BotInfo[]) => void
  setTradesForBot: (botId: number, trades: TradeRow[]) => void
  loadBots: (userId: number) => Promise<void>
  loadTradesForBot: (userId: number, botId: number) => Promise<void>
  loadAll: (userId: number) => Promise<void>
}

export const useData = create<DataState>((set, get) => ({
  bots: [],
  tradesByBot: {},
  setBots: (bots) => set({ bots }),
  setTradesForBot: (botId, trades) => set((s) => ({ tradesByBot: { ...s.tradesByBot, [botId]: trades } })),
  async loadBots(userId: number) {
    const res = await api.get(`/users/${userId}/bots`)
    set({ bots: res.data || [] })
  },
  async loadTradesForBot(userId: number, botId: number) {
    try {
      const res = await api.get(`/users/${userId}/bots/${botId}/trades-history`, { params: { mode: 'all' } })
      const rows = (res.data || []) as TradeRow[]
      set((s) => ({ tradesByBot: { ...s.tradesByBot, [botId]: rows } }))
    } catch {
      set((s) => ({ tradesByBot: { ...s.tradesByBot, [botId]: [] } }))
    }
  },
  async loadAll(userId: number) {
    await get().loadBots(userId)
    const bots = get().bots
    await Promise.all(bots.map(b => get().loadTradesForBot(userId, b.id)))
  },
}))
