"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { useRouter, usePathname } from "next/navigation";
import { auth as authApi } from "@/lib/api";
import { safeGetItem, safeSetItem, safeRemoveItem } from "@/lib/utils";
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

  // Check for existing token on mount; attempt refresh if expired
  useEffect(() => {
    const token = safeGetItem("auth_token");
    if (token) {
      authApi.me()
        .then((u) => setUser(u))
        .catch(async () => {
          // Token might be expired — try refresh
          const refreshToken = safeGetItem("refresh_token");
          if (refreshToken) {
            try {
              const res = await authApi.refresh({ refresh_token: refreshToken });
              safeSetItem("auth_token", res.access_token);
              safeSetItem("refresh_token", res.refresh_token);
              const u = await authApi.me();
              setUser(u);
              return;
            } catch {
              // Refresh also failed — truly expired
            }
          }
          safeRemoveItem("auth_token");
          safeRemoveItem("refresh_token");
          safeRemoveItem("auth_user");
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
    safeSetItem("auth_token", res.access_token);
    safeSetItem("refresh_token", res.refresh_token);
    safeSetItem("auth_user", JSON.stringify({
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
    safeSetItem("auth_token", res.access_token);
    safeSetItem("refresh_token", res.refresh_token);
    safeSetItem("auth_user", JSON.stringify({
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
    safeRemoveItem("auth_token");
    safeRemoveItem("refresh_token");
    safeRemoveItem("auth_user");
    setUser(null);
    router.push("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
