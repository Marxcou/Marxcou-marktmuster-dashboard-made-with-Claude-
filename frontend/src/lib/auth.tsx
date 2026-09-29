import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, type ReactNode } from "react";
import { api, setCsrfToken, type Me } from "./api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["me"],
    retry: false,
    staleTime: Infinity,
    queryFn: async () => {
      try {
        const me = await api<Me>("/auth/me");
        setCsrfToken(me.csrf_token);
        return me;
      } catch {
        return null;
      }
    },
  });

  const login = async (email: string, password: string) => {
    const me = await api<Me>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
    setCsrfToken(me.csrf_token);
    qc.setQueryData(["me"], me);
  };
  const logout = async () => {
    await api<void>("/auth/logout", { method: "POST" });
    setCsrfToken("");
    // Nicht qc.clear(): das entfernt auch die Abfrage "me", an der die Oberfläche hängt, und die Abmeldung bliebe ohne Wirkung
    qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
    qc.setQueryData(["me"], null);
  };

  const refresh = async () => {
    const me = await api<Me>("/auth/me");
    setCsrfToken(me.csrf_token);
    qc.setQueryData(["me"], me);
  };

  return <AuthContext.Provider value={{ me: data ?? null, loading: isLoading, login, logout, refresh }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("AuthProvider fehlt");
  return ctx;
}
