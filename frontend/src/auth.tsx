import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";
import { post, request, session } from "./lib/api";
import type { User } from "./types";
import { Loading } from "./components/ui";

interface AuthContextValue {
  user: User | null;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}
const AuthContext = createContext<AuthContextValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(!!session.get());
  const client = useQueryClient();
  useEffect(() => {
    if (session.get())
      request<User>("/auth/me")
        .then(setUser)
        .catch(() => session.clear())
        .finally(() => setLoading(false));
    const unauthorized = () => {
      setUser(null);
      client.clear();
    };
    window.addEventListener("geopol:unauthorized", unauthorized);
    return () =>
      window.removeEventListener("geopol:unauthorized", unauthorized);
  }, [client]);
  async function login(username: string, password: string) {
    const result = await post<{ token: string; user: User }>("/auth/login", {
      username,
      password,
    });
    session.set(result.token);
    client.clear();
    setUser(result.user);
  }
  async function logout() {
    try {
      await post("/auth/logout");
    } finally {
      session.clear();
      client.clear();
      setUser(null);
    }
  }
  return (
    <AuthContext.Provider value={{ user, login, logout }}>
      {loading ? <Loading text="Verificando sesión…" /> : children}
    </AuthContext.Provider>
  );
}
export const useAuth = () => {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is missing");
  return value;
};
