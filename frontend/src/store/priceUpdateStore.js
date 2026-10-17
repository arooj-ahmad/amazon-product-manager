// src/store/useAppStore.js
import { create } from 'zustand'

export const useAppStore = create((set) => ({
  isAppInitialized: false,
  shopDomain: '',
  subscription: null,
  collections: [],
  storeMarkup: null,
  
  setAppInitialized: (val) => set({ isAppInitialized: val }),
  setShopDomain: (domain) => set({ shopDomain: domain }),
  setSubscription: (sub) => set({ subscription: sub }),
  setCollections: (collections) => set({ collections }),
  setStoreMarkup: (markup) => set({ storeMarkup: markup }),
}))