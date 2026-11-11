import React, { createContext, useContext, useEffect, useState } from "react";
import { apiClient, getStoredToken, setStoredToken } from "../api/client";
import type { User } from "../types/api";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshUser = async () => {
    try {
      const me = await apiClient.getMe();
      setUser(me);
    } catch {
      setUser(null);
      setStoredToken(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    // Attempt restoring session via HttpOnly cookie or stored JWT
    if (getStoredToken()) {
      void refreshUser();
    } else {
      void refreshUser();
    }
  }, []);

  const login = async (email: string, password: string) => {
    const res = await apiClient.login({ email, password });
    setUser(res.user);
  };

  const register = async (name: string, email: string, password: string) => {
    const res = await apiClient.register({ name, email, password });
    setUser(res.user);
  };

  const logout = async () => {
    await apiClient.logout();
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return ctx;
}
