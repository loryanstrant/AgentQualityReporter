import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, clearToken, getToken, setToken } from "../api/client";

interface User {
  username: string;
  role: string;
}
interface AuthState {
  user: User | null;
  loading: boolean;
  entraAvailable: boolean;
  login: (username: string, password: string) => Promise<void>;
  loginEntra: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState>(null!);
export const useAuth = () => useContext(AuthContext);

interface TokenResp {
  access_token: string;
  username: string;
  role: string;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [entraAvailable, setEntraAvailable] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const mode = await api.get<{ entra_available: boolean }>("/auth/mode");
        setEntraAvailable(mode.entra_available);
      } catch {
        /* ignore */
      }
      if (getToken()) {
        try {
          const me = await api.get<User>("/auth/me");
          setUser(me);
        } catch {
          clearToken();
        }
      }
      setLoading(false);
    })();
  }, []);

  const login = async (username: string, password: string) => {
    const r = await api.post<TokenResp>("/auth/login", { username, password });
    setToken(r.access_token);
    setUser({ username: r.username, role: r.role });
  };

  const loginEntra = async () => {
    const r = await api.post<TokenResp>("/auth/entra");
    setToken(r.access_token);
    setUser({ username: r.username, role: r.role });
  };

  const logout = () => {
    clearToken();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, entraAvailable, login, loginEntra, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
