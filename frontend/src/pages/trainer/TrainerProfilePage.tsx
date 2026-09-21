import AccountDetailsCard from "../../components/AccountDetailsCard";
import ChangePasswordCard from "../../components/ChangePasswordCard";
import MfaCard from "../../components/MfaCard";
import { PageHeader } from "../../components/ui";

/**
 * A trainer's own account.
 *
 * This used to edit their instructor profile -- the name, bio and photo shown
 * on the public instructors page. Instructor profiles have been removed, so
 * what is left to manage here is the account itself.
 */
export default function TrainerProfilePage() {
  return (
    <div>
      <PageHeader title="My Profile" subtitle="Your account, password and two-step sign-in." />
      <div className="flex flex-col gap-6">
        <AccountDetailsCard />
        <MfaCard />
        <ChangePasswordCard />
      </div>
    </div>
  );
}
