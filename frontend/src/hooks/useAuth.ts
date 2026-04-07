import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../stores/authStore';
import { authApi } from '../api/client';
import type { Role } from '../types';

export function useAuth() {
  const { user, token, isAuthenticated, login, logout } = useAuthStore();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = async (email: string, password: string) => {
    setLoading(true);
    setError(null);
    try {
      const tokenRes = await authApi.login(email, password);
      const accessToken: string = tokenRes.data.access_token;

      // Decode role from JWT payload (base64)
      const payload = JSON.parse(atob(accessToken.split('.')[1]));

      login({
        id: payload.sub || '',
        email: payload.email || email,
        first_name: (payload.email || email).split('@')[0],
        last_name: '',
        role: (payload.role || 'employee') as Role,
        token: accessToken,
      });
      navigate('/dashboard');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string; code?: string };
      const msg = e.response?.data?.detail || e.message || 'Connexion échouée';
      setError(`${msg}${e.code ? ` (${e.code})` : ''}`);
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
    role: Role;
  }) => {
    setLoading(true);
    setError(null);
    try {
      // Step 1: register (returns UserRead, no token)
      await authApi.register(data);

      // Step 2: auto-login to get token
      const tokenRes = await authApi.login(data.email, data.password);
      const accessToken: string = tokenRes.data.access_token;

      login({
        id: '',
        email: data.email,
        first_name: data.first_name,
        last_name: data.last_name,
        role: data.role,
        token: accessToken,
      });
      navigate('/dashboard');
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } }; message?: string };
      setError(e.response?.data?.detail || e.message || 'Inscription échouée');
    } finally {
      setLoading(false);
    }
  };

  const signOut = () => {
    logout();
    navigate('/login');
  };

  return { user, token, isAuthenticated, loading, error, setError, signIn, signUp, signOut };
}
