import api from './api';

// ─── Types ────────────────────────────────────────────────────────────────────
export interface ActionItem {
  id: string;
  title: string;
  description?: string;
  assignee_id?: string;
  assignee_name?: string;
  status: 'todo' | 'in_progress' | 'done' | 'cancelled';
  priority: 'low' | 'medium' | 'high' | 'urgent';
  due_date?: string;
  meeting_id?: string;
  source: 'transcript' | 'manual';
  jira_id?: string;
  linear_id?: string;
  notion_id?: string;
  created_at: string;
  updated_at: string;
}

export interface CreateActionItem {
  title: string;
  description?: string;
  assignee_name?: string;
  status?: ActionItem['status'];
  priority?: ActionItem['priority'];
  due_date?: string;
  meeting_id?: string;
}

export interface ActionItemStats {
  total: number;
  todo: number;
  in_progress: number;
  done: number;
  overdue: number;
}

// ─── API calls ────────────────────────────────────────────────────────────────
export const tasksApi = {
  list: (params?: { status?: string; meeting_id?: string; limit?: number }) =>
    api.get<ActionItem[]>('/action-items', { params }).then(r => r.data),

  get: (id: string) =>
    api.get<ActionItem>(`/action-items/${id}`).then(r => r.data),

  create: (data: CreateActionItem) =>
    api.post<ActionItem>('/action-items', data).then(r => r.data),

  update: (id: string, data: Partial<ActionItem>) =>
    api.patch<ActionItem>(`/action-items/${id}`, data).then(r => r.data),

  delete: (id: string) =>
    api.delete(`/action-items/${id}`).then(r => r.data),

  reorder: (ids: string[]) =>
    api.post('/action-items/reorder', { ids }).then(r => r.data),

  getStats: () =>
    api.get<ActionItemStats>('/action-items/stats').then(r => r.data),

  syncToJira: (id: string) =>
    api.post(`/action-items/${id}/sync/jira`).then(r => r.data),

  syncToLinear: (id: string) =>
    api.post(`/action-items/${id}/sync/linear`).then(r => r.data),

  syncToNotion: (id: string) =>
    api.post(`/action-items/${id}/sync/notion`).then(r => r.data),
};

export default tasksApi;
