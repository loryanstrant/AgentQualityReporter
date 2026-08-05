import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import OverviewPage from "./pages/OverviewPage";
import AgentDetailPage from "./pages/AgentDetailPage";
import HistoryPage from "./pages/HistoryPage";
import AdminPage from "./pages/AdminPage";
import RulesPage from "./pages/RulesPage";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="h-full grid place-items-center text-slate">
        Loading…
      </div>
    );
  }

  if (!user) {
    return (
      <Routes>
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/agents/:botId" element={<AgentDetailPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route
          path="/settings"
          element={user.role === "admin" ? <AdminPage /> : <Navigate to="/" replace />}
        />
        <Route
          path="/rules"
          element={user.role === "admin" ? <RulesPage /> : <Navigate to="/" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
