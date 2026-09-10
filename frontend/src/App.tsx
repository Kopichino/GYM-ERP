import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./components/layout/AppLayout";
import LoadingScreen from "./components/LoadingScreen";
import { useAuthBootstrap } from "./hooks/useAuthBootstrap";
import { useBranding } from "./hooks/useBranding";
import AnnouncementsPage from "./pages/AnnouncementsPage";
import BillingPage from "./pages/BillingPage";
import DashboardPage from "./pages/DashboardPage";
import ExercisesPage from "./pages/ExercisesPage";
import GalleryPage from "./pages/GalleryPage";
import InstructorsPage from "./pages/InstructorsPage";
import LandingPage from "./pages/LandingPage";
import LoginPage from "./pages/LoginPage";
import SchedulePage from "./pages/SchedulePage";
import SignupPage from "./pages/SignupPage";
import WorkoutsPage from "./pages/WorkoutsPage";
import AdminRoute from "./routes/AdminRoute";
import MemberRoute from "./routes/MemberRoute";
import ProtectedRoute from "./routes/ProtectedRoute";
import TrainerRoute from "./routes/TrainerRoute";

// Recharts (progress page) and the admin/trainer subtrees are only visited by
// a subset of users -- code-split them out of the main bundle.
const ProgressPage = lazy(() => import("./pages/ProgressPage"));
const ProfilePage = lazy(() => import("./pages/ProfilePage"));
const SplitPage = lazy(() => import("./pages/SplitPage"));
const DietPage = lazy(() => import("./pages/DietPage"));
const ReferralsPage = lazy(() => import("./pages/ReferralsPage"));
const AchievementsPage = lazy(() => import("./pages/AchievementsPage"));
const BookTrainerPage = lazy(() => import("./pages/BookTrainerPage"));
const AdminLayout = lazy(() => import("./components/layout/AdminLayout"));
const AdminOverviewPage = lazy(() => import("./pages/admin/AdminOverviewPage"));
const AdminMembersPage = lazy(() => import("./pages/admin/AdminMembersPage"));
const AdminTrainersPage = lazy(() => import("./pages/admin/AdminTrainersPage"));
const AdminEnquiriesPage = lazy(() => import("./pages/admin/AdminEnquiriesPage"));
const AdminImportPage = lazy(() => import("./pages/admin/AdminImportPage"));
const AdminDevicesPage = lazy(() => import("./pages/admin/AdminDevicesPage"));
const AdminAnnouncementsPage = lazy(() => import("./pages/admin/AdminAnnouncementsPage"));
const AdminInstructorsPage = lazy(() => import("./pages/admin/AdminInstructorsPage"));
const AdminSchedulePage = lazy(() => import("./pages/admin/AdminSchedulePage"));
const AdminGalleryPage = lazy(() => import("./pages/admin/AdminGalleryPage"));
const AdminBillingPage = lazy(() => import("./pages/admin/AdminBillingPage"));
const AdminPlansPage = lazy(() => import("./pages/admin/AdminPlansPage"));
const AdminOffersPage = lazy(() => import("./pages/admin/AdminOffersPage"));
const AdminExpensesPage = lazy(() => import("./pages/admin/AdminExpensesPage"));
const AdminReportsPage = lazy(() => import("./pages/admin/AdminReportsPage"));
const AdminKioskPage = lazy(() => import("./pages/admin/AdminKioskPage"));
const AdminReferralsPage = lazy(() => import("./pages/admin/AdminReferralsPage"));
const AdminRetentionPage = lazy(() => import("./pages/admin/AdminRetentionPage"));
const AdminBadgesPage = lazy(() => import("./pages/admin/AdminBadgesPage"));
const AdminShiftsPage = lazy(() => import("./pages/admin/AdminShiftsPage"));
const AdminDayPassesPage = lazy(() => import("./pages/admin/AdminDayPassesPage"));
const AdminWhatsAppPage = lazy(() => import("./pages/admin/AdminWhatsAppPage"));
const AdminBrandingPage = lazy(() => import("./pages/admin/AdminBrandingPage"));
const AdminDomainsPage = lazy(() => import("./pages/admin/AdminDomainsPage"));
const AdminEmailPage = lazy(() => import("./pages/admin/AdminEmailPage"));
const AdminWebsiteFormPage = lazy(
  () => import("./pages/admin/AdminWebsiteFormPage"),
);
const AdminFeedbackPage = lazy(() => import("./pages/admin/AdminFeedbackPage"));
const QrCheckInPage = lazy(() => import("./pages/QrCheckInPage"));
const TrainerDashboardPage = lazy(() => import("./pages/trainer/TrainerDashboardPage"));
const TrainerMembersPage = lazy(() => import("./pages/trainer/TrainerMembersPage"));
const TrainerMemberDetailPage = lazy(() => import("./pages/trainer/TrainerMemberDetailPage"));
const TrainerSchedulePage = lazy(() => import("./pages/trainer/TrainerSchedulePage"));
const TrainerProfilePage = lazy(() => import("./pages/trainer/TrainerProfilePage"));
const TrainerPTPage = lazy(() => import("./pages/trainer/TrainerPTPage"));

export default function App() {
  const { ready, slow } = useAuthBootstrap();
  // Painted onto :root before anything renders, so the login screen already
  // carries the gym's colours.
  useBranding();

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
          {/* Shared gym content -- any signed-in role can read these. */}
          <Route path="/exercises" element={<ExercisesPage />} />
          <Route path="/announcements" element={<AnnouncementsPage />} />
          <Route path="/instructors" element={<InstructorsPage />} />
          <Route path="/schedule" element={<SchedulePage />} />
          <Route path="/gallery" element={<GalleryPage />} />
          {/* Where a scanned front-desk QR lands. Any role can record a
              visit, so this sits alongside the shared pages. */}
          <Route path="/check-in" element={<QrCheckInPage />} />

          {/* Member portal */}
          <Route element={<MemberRoute />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/workouts" element={<WorkoutsPage />} />
            <Route path="/split" element={<SplitPage />} />
            <Route path="/diet" element={<DietPage />} />
            <Route path="/referrals" element={<ReferralsPage />} />
            <Route path="/achievements" element={<AchievementsPage />} />
            <Route path="/book-trainer" element={<BookTrainerPage />} />
            <Route path="/progress" element={<ProgressPage />} />
            <Route path="/profile" element={<ProfilePage />} />
            <Route path="/billing" element={<BillingPage />} />
          </Route>

          {/* Trainer portal */}
          <Route element={<TrainerRoute />}>
            <Route path="/trainer" element={<TrainerDashboardPage />} />
            <Route path="/trainer/members" element={<TrainerMembersPage />} />
            <Route path="/trainer/members/:memberId" element={<TrainerMemberDetailPage />} />
            <Route path="/trainer/schedule" element={<TrainerSchedulePage />} />
            <Route path="/trainer/pt" element={<TrainerPTPage />} />
            <Route path="/trainer/profile" element={<TrainerProfilePage />} />
          </Route>

          {/* Admin portal */}
          <Route element={<AdminRoute />}>
            <Route path="/admin" element={<AdminLayout />}>
              {/* The owner dashboard is what an admin should land on: the
                  member list is a place you go for a reason, not a summary. */}
              <Route index element={<AdminOverviewPage />} />
              <Route path="members" element={<AdminMembersPage />} />
              <Route path="trainers" element={<AdminTrainersPage />} />
              <Route path="enquiries" element={<AdminEnquiriesPage />} />
              <Route path="import" element={<AdminImportPage />} />
              <Route path="devices" element={<AdminDevicesPage />} />
              <Route path="announcements" element={<AdminAnnouncementsPage />} />
              <Route path="instructors" element={<AdminInstructorsPage />} />
              <Route path="schedule" element={<AdminSchedulePage />} />
              <Route path="gallery" element={<AdminGalleryPage />} />
              <Route path="billing" element={<AdminBillingPage />} />
              <Route path="plans" element={<AdminPlansPage />} />
              <Route path="offers" element={<AdminOffersPage />} />
              <Route path="expenses" element={<AdminExpensesPage />} />
              <Route path="reports" element={<AdminReportsPage />} />
              <Route path="kiosk" element={<AdminKioskPage />} />
              <Route path="referrals" element={<AdminReferralsPage />} />
              <Route path="retention" element={<AdminRetentionPage />} />
              <Route path="badges" element={<AdminBadgesPage />} />
              <Route path="shifts" element={<AdminShiftsPage />} />
              <Route path="day-passes" element={<AdminDayPassesPage />} />
              <Route path="whatsapp" element={<AdminWhatsAppPage />} />
              <Route path="feedback" element={<AdminFeedbackPage />} />
              <Route path="branding" element={<AdminBrandingPage />} />
              <Route path="domains" element={<AdminDomainsPage />} />
              <Route path="email" element={<AdminEmailPage />} />
              <Route path="website-form" element={<AdminWebsiteFormPage />} />
            </Route>
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
  );
}
