import { create } from 'zustand'

export type ToastKind = 'success' | 'danger' | 'warning' | 'info'

type Toast = { id: string; kind: ToastKind; message: string }

type ToastState = {
  toasts: Toast[]
  show: (kind: ToastKind, message: string) => void
  dismiss: (id: string) => void
}

const DURATION_MS = 4000
// Id local de cada aviso. Un contador basta (crypto.randomUUID no existe sin HTTPS).
let nextId = 0

export const useToastStore = create<ToastState>()((set, get) => ({
  toasts: [],
  show: (kind, message) => {
    const id = String(++nextId)
    set((s) => ({ toasts: [...s.toasts, { id, kind, message }] }))
    setTimeout(() => get().dismiss(id), DURATION_MS)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

// Atajo para usar fuera de componentes o en manejadores: toast.success('Guardado')
export const toast = {
  success: (message: string) => useToastStore.getState().show('success', message),
  error: (message: string) => useToastStore.getState().show('danger', message),
  warning: (message: string) => useToastStore.getState().show('warning', message),
  info: (message: string) => useToastStore.getState().show('info', message),
}
