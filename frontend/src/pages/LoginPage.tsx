import { FormEvent, useState } from "react";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { login, loginEntra, entraAvailable } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError((err as Error).message === "unauthorized" ? "Invalid credentials" : "Incorrect username or password");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-full grid place-items-center p-6">
      <div className="card p-8 w-full max-w-sm">
        <div className="flex items-center gap-2 mb-6">
          <span className="w-3 h-6 rounded-sm bg-orange inline-block" />
          <h1 className="font-semibold text-lg text-ink">Agent Quality Platform</h1>
        </div>

        {entraAvailable && (
          <>
            <button
              onClick={() => loginEntra().catch((e) => setError((e as Error).message))}
              className="w-full mb-4 py-2 rounded-lg bg-strong text-white font-medium hover:opacity-90"
            >
              Sign in with Microsoft Entra ID
            </button>
            <div className="text-center text-xs text-slate mb-4">or use an admin account</div>
          </>
        )}

        <form onSubmit={submit} className="space-y-3">
          <input
            className="w-full border border-hairline rounded-lg px-3 py-2"
            placeholder="Username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
          />
          <input
            className="w-full border border-hairline rounded-lg px-3 py-2"
            type="password"
            placeholder="Password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <div className="text-fail text-sm">{error}</div>}
          <button
            disabled={busy}
            className="w-full py-2 rounded-lg bg-orange text-white font-medium hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
