"use client";

import React, { createContext, useState, useContext, ReactNode, useEffect } from "react";

interface AuthContextType {
  user: { name: string, email: string, avatar: string, organization: string } | null;
  login: (user: { name: string, email: string, avatar: string, organization: string }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  login: () => {},
  logout: () => {},
});
const AUTH_STORAGE_KEY = "kair-auth-status";

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<{ name: string, email: string, avatar: string, organization: string } | null>(null);

  const login = (user: { name: string, email: string, avatar: string, organization: string }) => setUser(user);
  const logout = () => setUser(null);

  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);