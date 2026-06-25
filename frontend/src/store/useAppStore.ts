import { create } from "zustand";
import type {
  Meeting,
  ActionItem,
  AutomationRule,
  Integration,
  ChatConversation,
  Project,
  TranscriptSegment,
} from "../types";
import {
  mockMeetings,
  mockActionItems,
  mockAutomations,
  mockIntegrations,
  mockProjects,
  mockConversations,
} from "../data/mockDb";

interface AppState {
  meetings: Meeting[];
  actionItems: ActionItem[];
  automations: AutomationRule[];
  integrations: Integration[];
  projects: Project[];
  conversations: ChatConversation[];
  activeConversationId: string | null;
  liveSegments: TranscriptSegment[];
  
  // Actions
  toggleActionItemStatus: (id: string) => void;
  updateActionItemStatus: (id: string, status: ActionItem["status"]) => void;
  addActionItem: (item: Omit<ActionItem, "id" | "createdAt">) => void;
  toggleAutomationActive: (id: string) => void;
  toggleIntegrationStatus: (id: string) => void;
  addMeeting: (meeting: Omit<Meeting, "id">) => string;
  addChatMessage: (convId: string, content: string, role: "user" | "assistant") => void;
  createNewConversation: (title: string) => string;
  setActiveConversationId: (id: string | null) => void;
  addLiveSegment: (segment: TranscriptSegment) => void;
  clearLiveSegments: () => void;
  updateMeetingStatus: (id: string, status: Meeting["status"]) => void;
}

export const useAppStore = create<AppState>((set) => ({
  meetings: mockMeetings,
  actionItems: mockActionItems,
  automations: mockAutomations,
  integrations: mockIntegrations,
  projects: mockProjects,
  conversations: mockConversations,
  activeConversationId: mockConversations[0]?.id || null,
  liveSegments: [],

  toggleActionItemStatus: (id) =>
    set((state) => ({
      actionItems: state.actionItems.map((item) =>
        item.id === id
          ? {
              ...item,
              status: item.status === "done" ? "pending" : "done",
            }
          : item
      ),
    })),

  updateActionItemStatus: (id, status) =>
    set((state) => ({
      actionItems: state.actionItems.map((item) =>
        item.id === id ? { ...item, status } : item
      ),
    })),

  addActionItem: (item) =>
    set((state) => {
      const newItem: ActionItem = {
        ...item,
        id: `act_${state.actionItems.length + 1}`,
        createdAt: new Date().toISOString(),
      };
      return { actionItems: [...state.actionItems, newItem] };
    }),

  toggleAutomationActive: (id) =>
    set((state) => ({
      automations: state.automations.map((item) =>
        item.id === id ? { ...item, isActive: !item.isActive } : item
      ),
    })),

  toggleIntegrationStatus: (id) =>
    set((state) => ({
      integrations: state.integrations.map((item) =>
        item.id === id
          ? {
              ...item,
              status: item.status === "connected" ? "disconnected" : "connected",
              lastSync: item.status === "connected" ? undefined : new Date().toISOString(),
            }
          : item
      ),
    })),

  addMeeting: (meeting) => {
    const id = `meet_${Math.random().toString(36).substr(2, 9)}`;
    const newMeeting: Meeting = {
      ...meeting,
      id,
    };
    set((state) => ({
      meetings: [newMeeting, ...state.meetings],
    }));
    return id;
  },

  addChatMessage: (convId, content, role) =>
    set((state) => ({
      conversations: state.conversations.map((c) => {
        if (c.id === convId) {
          const newMessage = {
            id: `msg_${Date.now()}`,
            role,
            content,
            timestamp: new Date().toISOString(),
            citations:
              role === "assistant" && content.includes("Azure")
                ? [
                    {
                      meetingId: "meet_2",
                      meetingTitle: "Azure Migration Strategy Planning",
                      timestamp: "00:14:32",
                      speaker: "Jay Shah",
                      snippet: "...we decided to commit to Azure Blob Storage because we have Azure credits that cover it...",
                    },
                  ]
                : undefined,
            suggestedQuestions:
              role === "assistant"
                ? ["Explain the Redis timeline.", "Who is responsible for Faster-Whisper benchmarks?"]
                : undefined,
          };
          return {
            ...c,
            messages: [...c.messages, newMessage],
          };
        }
        return c;
      }),
    })),

  createNewConversation: (title) => {
    const id = `chat_${Date.now()}`;
    const newConv: ChatConversation = {
      id,
      title,
      createdAt: new Date().toISOString(),
      messages: [],
    };
    set((state) => ({
      conversations: [newConv, ...state.conversations],
      activeConversationId: id,
    }));
    return id;
  },

  setActiveConversationId: (id) => set({ activeConversationId: id }),

  addLiveSegment: (segment) =>
    set((state) => ({
      liveSegments: [...state.liveSegments, segment],
    })),

  clearLiveSegments: () => set({ liveSegments: [] }),

  updateMeetingStatus: (id, status) =>
    set((state) => ({
      meetings: state.meetings.map((m) =>
        m.id === id ? { ...m, status, endedAt: status === "completed" ? new Date().toISOString() : undefined } : m
      ),
    })),
}));
