import AccountDetailsCard from "../../components/AccountDetailsCard";
import ChangePasswordCard from "../../components/ChangePasswordCard";
import MfaCard from "../../components/MfaCard";

/**
 * The signed-in admin's own account.
 *
 * Members and trainers each have a profile page for their password and two-step
 * sign-in; the admin portal had nowhere. The heading comes from the layout, as
 * it does for every admin page.
 */
export default function AdminAccountPage() {
  return (
    <div className="flex flex-col gap-6">
      <AccountDetailsCard />
      <MfaCard />
      <ChangePasswordCard />
    </div>
  );
}
