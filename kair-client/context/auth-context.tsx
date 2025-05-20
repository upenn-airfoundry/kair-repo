"use client";

import React, { createContext, useState, useContext, ReactNode, useEffect } from "react";

interface AuthContextType {
  isAuthenticated: boolean;
  login: () => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const AUTH_STORAGE_KEY = "kair-auth-status";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
        const storedAuth = localStorage.getItem(AUTH_STORAGE_KEY);
        return storedAuth === "true";
    }
    return false;
  });

  useEffect(() => {
    if (typeof window !== "undefined") {
      localStorage.setItem(AUTH_STORAGE_KEY, String(isAuthenticated));
    }
  }, [isAuthenticated]);

  const login = () => {
    setIsAuthenticated(true);
  };

  const logout = () => {
    setIsAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
} 