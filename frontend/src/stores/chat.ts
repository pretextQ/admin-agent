import { create } from "zustand";
import type { Message } from "@/types";

interface ChatState {
  conversationId: string | null;
  messages: Message[];
  isTyping: boolean;
  addMessage: (msg: Message) => void;
  setMessages: (msgs: Message[]) => void;
  setTyping: (typing: boolean) => void;
  setConversationId: (id: string) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  conversationId: null,
  messages: [],
  isTyping: false,
  addMessage: (msg) => set((s) => ({ messages: [...s.messages, msg] })),
  setMessages: (msgs) => set({ messages: msgs }),
  setTyping: (typing) => set({ isTyping: typing }),
  setConversationId: (id) => set({ conversationId: id }),
  clearMessages: () => set({ messages: [], conversationId: null }),
}));
