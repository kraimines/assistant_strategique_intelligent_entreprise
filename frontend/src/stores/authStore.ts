import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { User, Role } from '../types';

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  login: (user: User) => void;
  logout: () => void;
  updateRole: (role: Role) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      login: (user: User) => {
        set({ user, token: user.token, isAuthenticated: true });
      },

      logout: () => {
        set({ user: null, token: null, isAuthenticated: false });
      },

      updateRole: (role: Role) => {
        set((state) => ({
          user: state.user ? { ...state.user, role } : null,
        }));
      },
    }),
    {
      name: 'talan-auth-v2',
      partialize: (state) => ({
        user: state.user,
        token: state.token,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
