import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import api from '../services/api';

interface User {
  id: string;
  email: string;
  display_name: string;
  avatar_url?: string;
  role: string;
  org_id?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string, orgName?: string) => Promise<void>;
  logout: () => void;
  clearError: () => void;
  refreshUser: () => Promise<void>;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email, password) => {
        set({ isLoading: true, error: null });
        try {
          const { data } = await api.post('/auth/login', { email, password });
          localStorage.setItem('zapper_token', data.access_token);
          localStorage.setItem('zapper_refresh', data.refresh_token);
          set({
            user: data.user,
            token: data.access_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (err: any) {
          const msg = err?.response?.data?.detail || 'Invalid email or password';
          set({ error: msg, isLoading: false });
          throw err;
        }
      },

      register: async (email, password, displayName, orgName) => {
        set({ isLoading: true, error: null });
        try {
          const { data } = await api.post('/auth/register', {
            email,
            password,
            display_name: displayName,
            org_name: orgName,
          });
          localStorage.setItem('zapper_token', data.access_token);
          localStorage.setItem('zapper_refresh', data.refresh_token);
          set({
            user: data.user,
            token: data.access_token,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (err: any) {
          const msg = err?.response?.data?.detail || 'Registration failed';
          set({ error: msg, isLoading: false });
          throw err;
        }
      },

      logout: () => {
        localStorage.removeItem('zapper_token');
        localStorage.removeItem('zapper_refresh');
        set({ user: null, token: null, isAuthenticated: false });
        window.location.href = '/login';
      },

      clearError: () => set({ error: null }),

      refreshUser: async () => {
        try {
          const { data } = await api.get('/auth/me');
          set({ user: data, isAuthenticated: true });
        } catch {
          get().logout();
        }
      },
    }),
    {
      name: 'zapper-auth',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
