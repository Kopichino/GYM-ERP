import BodyStatsPanel from "../components/BodyStatsPanel";
import ChangePasswordCard from "../components/ChangePasswordCard";
import MfaCard from "../components/MfaCard";
import { PageHeader } from "../components/ui";
import { useAuthStore } from "../store/authStore";

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const name = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim() || user?.username;

  return (
    <div>
      <PageHeader
        title={name ? `${name}'s Profile` : "My Profile"}
        subtitle="Your measurements, BMI, goals, password and two-step sign-in."
      />
      <BodyStatsPanel />
      <div className="mt-6 flex flex-col gap-6">
        <MfaCard />
        <ChangePasswordCard />
      </div>
    </div>
  );
}
