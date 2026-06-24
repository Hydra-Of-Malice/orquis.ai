import React, { useEffect } from "react";
import { Routes, Route, Navigate, useNavigate, useLocation } from "react-router-dom";
import { Shell } from "./components/layout/Shell";
import { Dashboard } from "./pages/Dashboard";
import { MeetingsList } from "./pages/MeetingsList";
import { MeetingDetail } from "./pages/MeetingDetail";
import { LiveMeeting } from "./pages/LiveMeeting";
import { Search } from "./pages/Search";
import { AIChat } from "./pages/AIChat";
import { Tasks } from "./pages/Tasks";
import { Analytics } from "./pages/Analytics";
import { Automations } from "./pages/Automations";
import { Integrations } from "./pages/Integrations";
import { Settings } from "./pages/Settings";
import { Landing } from "./pages/Landing";
import Login from "./pages/Login";
import { Knowledge } from "./pages/Knowledge";
import { useAuthStore } from "./store/authStore";

/** Protect all app routes — redirect to /login if not authenticated. */
const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuthStore();
  const location = useLocation();
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
};

export const App: React.FC = () => {
  const { isAuthenticated, refreshUser } = useAuthStore();

  // On app mount, rehydrate user profile if we have a token
  useEffect(() => {
    const token = localStorage.getItem("zapper_token");
    if (token && isAuthenticated) {
      refreshUser();
    }
  }, []);

  return (
    <Routes>
      {/* Landing page — public */}
      <Route path="/" element={<Landing />} />

      {/* Auth pages — public */}
      <Route path="/login" element={<Login />} />

      {/* App pages — protected, inside Shell */}
      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <Shell>
              <Routes>
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/meetings/live" element={<MeetingsList defaultFilter="live" />} />
                <Route path="/meetings/upcoming" element={<MeetingsList defaultFilter="upcoming" />} />
                <Route path="/meetings/recordings" element={<MeetingsList defaultFilter="recordings" />} />
                <Route path="/meetings/:id" element={<MeetingDetail />} />
                <Route path="/live/:id" element={<LiveMeeting />} />
                <Route path="/search" element={<Search />} />
                <Route path="/knowledge/topics" element={<Knowledge />} />
                <Route path="/knowledge/projects" element={<Knowledge />} />
                <Route path="/knowledge/people" element={<Knowledge />} />
                <Route path="/chat" element={<AIChat />} />
                <Route path="/tasks" element={<Tasks />} />
                <Route path="/analytics/overview" element={<Analytics />} />
                <Route path="/analytics/team" element={<Analytics />} />
                <Route path="/analytics/coaching" element={<Analytics />} />
                <Route path="/automations" element={<Automations />} />
                <Route path="/integrations" element={<Integrations />} />
                <Route path="/settings" element={<Settings />} />
              </Routes>
            </Shell>
          </ProtectedRoute>
        }
      />
    </Routes>
  );
};

export default App;
