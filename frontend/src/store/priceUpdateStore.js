// src/store/priceUpdateStore.js
// ✅ Global state — page change pe bhi survive karta hai
import { create } from 'zustand'

export const usePriceUpdateStore = create((set, get) => ({
  // ── State ──
  cronRunning: false,
  cronMessage: null,
  cronProgress: {
    running: false,
    step: 0,
    total: 0,
    currentProduct: null,
    summary: null,
  },
  pollIntervalId: null,

  // ── Simple setters ──
  setCronRunning: (val) => set({ cronRunning: val }),
  setCronMessage: (val) => set({ cronMessage: val }),
  setCronProgress: (updater) =>
    set((state) => ({
      cronProgress:
        typeof updater === 'function'
          ? updater(state.cronProgress)
          : updater,
    })),

  // ── Polling ──
  startPolling: (apiUrl, idToken) => {
    // Agar already chal rahi hai toh pehle band karo
    const existing = get().pollIntervalId
    if (existing) clearInterval(existing)

    const intervalId = setInterval(async () => {
      try {
        const res = await fetch(
          `${apiUrl}/api/shopify/price-update-status`,
          {
            method: 'GET',
            headers: { Authorization: `Bearer ${idToken}` },
          }
        )

        if (!res.ok) return

        const data = await res.json()

        // Job abhi bhi chal raha hai
        if (data.running) {
          set((state) => ({
            cronProgress: {
              ...state.cronProgress,
              running: true,
              currentProduct: 'Processing products...',
            },
          }))
          return
        }

        // Job khatam — polling band
        get().stopPolling()

        const summary = data.summary || {}

        set({
          cronRunning: false,
          cronProgress: {
            running: false,
            step: summary.total || 0,
            total: summary.total || 0,
            currentProduct: null,
            summary: summary,
          },
        })

        if (summary.error) {
          set({
            cronMessage: {
              type: 'error',
              text: `❌ ${summary.error}`,
            },
          })
        } else {
          set({
            cronMessage: {
              type: 'success',
              text: `✅ Updated: ${summary.updated || 0}, Skipped: ${summary.skipped || 0}, Errors: ${summary.errors || 0}`,
            },
          })
        }

        // 30 sec baad auto-clear
        setTimeout(() => {
          set({
            cronMessage: null,
            cronProgress: {
              running: false,
              step: 0,
              total: 0,
              currentProduct: null,
              summary: null,
            },
          })
        }, 30000)
      } catch (err) {
        console.error('Polling error:', err)
      }
    }, 3000)

    set({ pollIntervalId: intervalId })
  },

  stopPolling: () => {
    const id = get().pollIntervalId
    if (id) {
      clearInterval(id)
      set({ pollIntervalId: null })
    }
  },
}))