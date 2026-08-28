import { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/AppShell";
import LoadingState from "./components/LoadingState";
import { useAuth } from "./lib/auth";
import { ToastProvider } from "./lib/toast";
import Alerts from "./pages/Alerts";
import AuthCallback from "./pages/AuthCallback";
import Communities from "./pages/Communities";
import Conversations from "./pages/Conversations";
import ConversationDetail from "./pages/ConversationDetail";
import Diagnostics from "./pages/Diagnostics";
import History from "./pages/History";
import Login from "./pages/Login";
import ManualImport from "./pages/ManualImport";
import RedditCallback from "./pages/RedditCallback";
import Settings from "./pages/Settings";
import Today from "./pages/Today";
import Topics from "./pages/Topics";

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { profile, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-surface">
        <LoadingState label="Cargando sesión…" />
      </div>
    );
  }
  if (!profile) return <Navigate to="/login" replace />;
  return <AppShell>{children}</AppShell>;
}

export default function App() {
  return (
    <ToastProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/auth/callback" element={<AuthCallback />} />
        <Route path="/" element={<Navigate to="/today" replace />} />
        <Route path="/today" element={<ProtectedRoute><Today /></ProtectedRoute>} />
        <Route path="/conversations" element={<ProtectedRoute><Conversations /></ProtectedRoute>} />
        <Route path="/conversations/:id" element={<ProtectedRoute><ConversationDetail /></ProtectedRoute>} />
        <Route path="/manual-import" element={<ProtectedRoute><ManualImport /></ProtectedRoute>} />
        <Route path="/communities" element={<ProtectedRoute><Communities /></ProtectedRoute>} />
        <Route path="/topics" element={<ProtectedRoute><Topics /></ProtectedRoute>} />
        <Route path="/history" element={<ProtectedRoute><History /></ProtectedRoute>} />
        <Route path="/alerts" element={<ProtectedRoute><Alerts /></ProtectedRoute>} />
        <Route path="/reddit/callback" element={<ProtectedRoute><RedditCallback /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/diagnostics" element={<ProtectedRoute><Diagnostics /></ProtectedRoute>} />
        <Route path="*" element={<Navigate to="/today" replace />} />
      </Routes>
    </ToastProvider>
  );
}
