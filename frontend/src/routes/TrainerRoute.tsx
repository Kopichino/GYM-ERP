import { Navigate, Outlet } from "react-router-dom";
import { homePathFor, useAuthStore } from "../store/authStore";

export default function TrainerRoute() {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "trainer") return <Navigate to={homePathFor(user)} replace />;
  return <Outlet />;
}
