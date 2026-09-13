import BodyStatsPanel from "../components/BodyStatsPanel";
import ChangePasswordCard from "../components/ChangePasswordCard";
import { PageHeader } from "../components/ui";
import { useAuthStore } from "../store/authStore";

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const name = `${user?.first_name ?? ""} ${user?.last_name ?? ""}`.trim() || user?.username;

  return (
    <div>
      <PageHeader
        title={name ? `${name}'s Profile` : "My Profile"}
        subtitle="Your measurements, BMI, goals and password."
      />
      <BodyStatsPanel />
      <div className="mt-6">
        <ChangePasswordCard />
      </div>
    </div>
  );
}
