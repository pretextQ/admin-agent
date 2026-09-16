import { create } from "zustand";

interface AppState {
  activeTab: "chat" | "tasks";
  setActiveTab: (tab: "chat" | "tasks") => void;
}

export const useAppStore = create<AppState>((set) => ({
  activeTab: "chat",
  setActiveTab: (tab) => set({ activeTab: tab }),
}));
