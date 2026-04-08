"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { auth as authApi } from "@/lib/api";
import type { AuthUser } from "@/lib/types";

interface AuthContextType {
  user: AuthUser | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  login: async () => {},
  register: async () => {},
  logout: () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

// Pages that don't require authentication
const PUBLIC_PATHS = ["/login"];

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  // Check for existing token on mount
  useEffect(() => {
    const token = localStorage.getItem("auth_token");
    if (token) {
      authApi.me()
        .then((u) => setUser(u))
        .catch(() => {
          // Token expired or invalid
          localStorage.removeItem("auth_token");
          localStorage.removeItem("auth_user");
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  // Redirect to login if not authenticated (after loading completes)
  useEffect(() => {
    if (!isLoading && !user && !PUBLIC_PATHS.includes(pathname)) {
      router.push("/login");
    }
  }, [isLoading, user, pathname, router]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await authApi.login({ email, password });
    localStorage.setItem("auth_token", res.access_token);
    localStorage.setItem("auth_user", JSON.stringify({
      id: res.user_id,
      email: res.email,
      display_name: res.display_name,
    }));
    setUser({
      id: res.user_id,
      email: res.email,
      display_name: res.display_name,
      created_at: new Date().toISOString(),
    });
    router.push("/projects");
  }, [router]);

  const register = useCallback(async (email: string, password: string, displayName?: string) => {
    const res = await authApi.register({ email, password, display_name: displayName });
    localStorage.setItem("auth_token", res.access_token);
    localStorage.setItem("auth_user", JSON.stringify({
      id: res.user_id,
      email: res.email,
      display_name: res.display_name,
    }));
    setUser({
      id: res.user_id,
      email: res.email,
      display_name: res.display_name,
      created_at: new Date().toISOString(),
    });
    router.push("/projects");
  }, [router]);

  const logout = useCallback(() => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
