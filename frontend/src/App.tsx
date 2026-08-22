import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import LoadingScreen from "./components/LoadingScreen";
import { useAuthBootstrap } from "./hooks/useAuthBootstrap";
import AnnouncementsPage from "./pages/AnnouncementsPage";
import DashboardPage from "./pages/DashboardPage";
import GalleryPage from "./pages/GalleryPage";
import InstructorsPage from "./pages/InstructorsPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import SchedulePage from "./pages/SchedulePage";
import SignupPage from "./pages/SignupPage";
import WorkoutsPage from "./pages/WorkoutsPage";
import AdminRoute from "./routes/AdminRoute";
import ProtectedRoute from "./routes/ProtectedRoute";

// Recharts (progress page) and the whole admin subtree are only visited by
// a subset of users -- code-split them out of the main bundle.
const ProgressPage = lazy(() => import("./pages/ProgressPage"));
const AdminLayout = lazy(() => import("./components/layout/AdminLayout"));
const AdminMembersPage = lazy(() => import("./pages/admin/AdminMembersPage"));
const AdminAnnouncementsPage = lazy(() => import("./pages/admin/AdminAnnouncementsPage"));
const AdminInstructorsPage = lazy(() => import("./pages/admin/AdminInstructorsPage"));
const AdminSchedulePage = lazy(() => import("./pages/admin/AdminSchedulePage"));
const AdminGalleryPage = lazy(() => import("./pages/admin/AdminGalleryPage"));

export default function App() {
  const { ready, slow } = useAuthBootstrap();

  if (!ready) {
    return <LoadingScreen label={slow ? "Waking up the server... this can take up to a minute on first load." : "Loading..."} />;
  }

  return (
    <Suspense fallback={<LoadingScreen />}>
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/workouts" element={<WorkoutsPage />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/announcements" element={<AnnouncementsPage />} />
          <Route path="/instructors" element={<InstructorsPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/gallery" element={<GalleryPage />} />

          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<AdminMembersPage />} />
              <Route path="announcements" element={<AdminAnnouncementsPage />} />
              <Route path="instructors" element={<AdminInstructorsPage />} />
              <Route path="schedule" element={<AdminSchedulePage />} />
              <Route path="gallery" element={<AdminGalleryPage />} />
            </Route>
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}
