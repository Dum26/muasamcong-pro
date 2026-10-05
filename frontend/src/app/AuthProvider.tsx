import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { authApi } from '../api/core';
import type { User } from '../types';

interface AuthState { user: User | null; loading: boolean; refresh: () => Promise<void>; logout: () => Promise<void> }
const Context = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  async function refresh() {
    try { setUser((await authApi.me()).user); }
    catch { setUser(null); }
    finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); const expired = () => setUser(null);
    window.addEventListener('msc:session-expired', expired);
    return () => window.removeEventListener('msc:session-expired', expired);
  }, []);
  async function logout() { try { await authApi.logout(); } finally { setUser(null); } }
  return <Context.Provider value={{ user, loading, refresh, logout }}>{children}</Context.Provider>;
}
export function useAuth(): AuthState {
  const state = useContext(Context);
  if (!state) throw new Error('AuthProvider missing');
  return state;
}
