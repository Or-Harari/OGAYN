import { create } from 'zustand'

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}

type UIState = {
  toasts: Toast[]
  addToast: (t: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  notifySuccess: (message: string, duration?: number) => void
  notifyError: (message: string, duration?: number) => void
  notifyInfo: (message: string, duration?: number) => void
}

export const useUI = create<UIState>((set, get) => ({
  toasts: [],
  addToast: (t) => {
    const id = Math.random().toString(36).slice(2)
    const toast: Toast = { id, duration: 3500, ...t }
    set((s) => ({ toasts: [...s.toasts, toast] }))
    // auto-remove
    setTimeout(() => {
      const current = get().toasts
      if (current.find((x) => x.id === id)) get().removeToast(id)
    }, toast.duration)
    return id
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  notifySuccess: (message, duration) => get().addToast({ type: 'success', message, duration }),
  notifyError: (message, duration) => get().addToast({ type: 'error', message, duration }),
  notifyInfo: (message, duration) => get().addToast({ type: 'info', message, duration }),
}))
