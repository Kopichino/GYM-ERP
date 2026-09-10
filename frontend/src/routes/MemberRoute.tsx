import { Navigate, Outlet } from "react-router-dom";
import { homePathFor, useAuthStore } from "../store/authStore";

/** Guards the member-only personal pages (check-in, own workouts, own
 *  billing). Admins and trainers get sent to their own portal instead. */
export default function MemberRoute() {
  const user = useAuthStore((s) => s.user);
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "member") return <Navigate to={homePathFor(user)} replace />;
  return <Outlet />;
}
