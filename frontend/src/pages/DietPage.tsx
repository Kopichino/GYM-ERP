import DietPlanner from "../components/DietPlanner";
import { PageHeader } from "../components/ui";

export default function DietPage() {
  return (
    <div>
      <PageHeader
        title="My Diet"
        subtitle="Plan what you eat each day. Calories and macros are worked out from your portions."
      />
      <DietPlanner />
    </div>
  );
}
