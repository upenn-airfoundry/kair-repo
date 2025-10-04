"use client";

import React, { createContext, useState, useContext, ReactNode, useEffect } from "react";

interface UserProfile {
  biosketch?: string;
  expertise?: string;
  projects?: string;
  publications?: any[];
  [key: string]: any;
}

interface AuthContextType {
  user: { 
    name: string, 
    email: string, 
    avatar: string, 
    organization: string,
    profile?: UserProfile | null,
    project_id?: number
  } | null;
  isLoading: boolean;
  login: (user: { name: string, email: string, avatar: string, organization: string, profile?: UserProfile | null, project_id: number }) => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  login: () => {},
  logout: () => {},
});
const AUTH_STORAGE_KEY = "kair-auth-status";

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<{
    name: string,
    email: string,
    avatar: string,
    organization: string,
    profile?: UserProfile | null,
    project_id?: number
  } | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // On mount, check for user in localStorage
    const storedUser = localStorage.getItem("user");
    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
    setIsLoading(false);
  }, []);

  const login = (user: {
    name: string,
    email: string,
    avatar: string,
    organization: string,
    profile?: UserProfile | null,
    project_id: number
  }) => {
    setUser(user);
    localStorage.setItem("user", JSON.stringify(user));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("user");
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}