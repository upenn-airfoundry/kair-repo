"use client";

import React, { createContext, useState, useContext, ReactNode, useEffect } from "react";

interface AuthContextType {
  user: { name: string, email: string, avatar: string, organization: string } | null;
  isLoading: boolean;
  login: (user: { name: string, email: string, avatar: string, organization: string }) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
});
const AUTH_STORAGE_KEY = "kair-auth-status";

export const AuthProvider = ({ children }: { children: React.ReactNode }) => {
  const [user, setUser] = useState<{ name: string, email: string, avatar: string, organization: string } | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // On mount, check for user in localStorage
    const storedUser = localStorage.getItem("user");
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setIsLoading(false);
  }, []);  

  const login = (user: { name: string, email: string, avatar: string, organization: string }) => {
    setUser(user);
    localStorage.setItem("user", JSON.stringify(user));
  }
  const logout = () => {
    setUser(null);
    localStorage.removeItem("user");
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);