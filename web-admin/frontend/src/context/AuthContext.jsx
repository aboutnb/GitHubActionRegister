import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { fetchCurrentUser } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);

  const refreshUser = async () => {
    try {
      const { data } = await fetchCurrentUser();
      setUser(data);
      return data;
    } catch {
      setUser(null);
      return null;
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    refreshUser();
  }, []);

  const value = useMemo(
    () => ({
      user,
      mustChangePassword: Boolean(user?.must_change_password),
      checking,
      setUser,
      refreshUser,
    }),
    [user, checking],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
