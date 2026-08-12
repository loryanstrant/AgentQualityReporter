import { ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";
import CopilotStudioLogo from "./CopilotStudioLogo";

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const loc = useLocation();

  const nav = [
    { to: "/", label: "Overview" },
    { to: "/history", label: "History" },
    ...(user?.role === "admin" ? [{ to: "/settings", label: "Admin" }] : []),
  ];

  const active = (to: string) =>
    to === "/" ? loc.pathname === "/" : loc.pathname.startsWith(to);

  return (
    <div className="min-h-full flex flex-col">
      <header className="bg-surface border-b border-line shadow-card sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center gap-6">
          <div className="flex items-center gap-2">
            <CopilotStudioLogo size={24} />
            <span className="font-semibold text-ink">
              Agent Quality <span className="text-slate font-normal">Platform</span>
            </span>
          </div>
          <nav className="flex gap-1">
            {nav.map((n) => (
              <Link
                key={n.to}
                to={n.to}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                  active(n.to)
                    ? "bg-mist text-ink"
                    : "text-slate hover:text-ink hover:bg-mist/60"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <div className="flex items-center gap-2">
              <span className="w-7 h-7 rounded-full bg-orange/15 text-orange grid place-items-center font-semibold uppercase">
                {(user?.username || "?").charAt(0)}
              </span>
              <span className="text-ink whitespace-nowrap max-w-[220px] truncate" title={user?.username}>
                {user?.username}
              </span>
              {user && user.role.toLowerCase() !== user.username.toLowerCase() && (
                <span className="pill bg-mist text-slate whitespace-nowrap">{user.role}</span>
              )}
            </div>
            <button
              onClick={toggle}
              title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              aria-label="Toggle theme"
              className="w-9 h-9 grid place-items-center rounded-lg border border-hairline hover:bg-mist text-ink"
            >
              {theme === "dark" ? "☀️" : "🌙"}
            </button>
            <button
              onClick={logout}
              className="px-3 py-1.5 rounded-lg border border-hairline hover:bg-mist text-ink whitespace-nowrap"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-6 py-6">{children}</main>
      <footer className="text-center text-xs text-slate py-4">
        Copilot Studio Agent Quality Platform · findings trace to the Patterns &amp; Practices deck
      </footer>
    </div>
  );
}
