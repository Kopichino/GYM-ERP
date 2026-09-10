import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/authStore";

export default function ProtectedRoute() {
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  // Carry the attempted URL through the login page, so a member who scans the
  // front-desk QR on a signed-out phone still lands on the check-in.
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  return <Outlet />;
}
