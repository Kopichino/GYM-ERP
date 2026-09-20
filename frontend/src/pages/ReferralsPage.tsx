import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState } from "react";
import {
  createReferral,
  fetchMyReferrals,
  type ReferralStatus,
} from "../api/referrals";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  Input,
  LoadingState,
  PageHeader,
  tableCellClass,
  tableHeadCellClass,
  tableHeadRowClass,
  tableRowClass,
} from "../components/ui";
import { useSubmitOnce } from "../hooks/useSubmitOnce";
import { serverMessage } from "../lib/apiError";
import { INVALID_EMAIL, looksLikeEmail } from "../lib/email";
import { fadeUp, staggerContainer } from "../lib/motion";
import { NOT_A_PHONE, looksDialable } from "../lib/phone";
import { railColor } from "../lib/theme";

const STATUS_COLOR: Record<ReferralStatus, string> = {
  pending: "#9494a8",
  signed_up: "#ffb020",
  joined: "#22c55e",
};

const STATUS_LABEL: Record<ReferralStatus, string> = {
  pending: "Not signed up",
  signed_up: "Signed up",
  joined: "Joined",
};

type Field = "name" | "phone" | "email";
const FIELDS: Field[] = ["name", "phone", "email"];
const EMPTY_FORM: Record<Field, string> = { name: "", phone: "", email: "" };

/** A refusal shown under the field it is about, and announced with it. */
function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null;
  return (
    <p id={id} className="mt-1 text-sm text-red-400">
      {message}
    </p>
  );
}

export default function ReferralsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(EMPTY_FORM);
  // Per field, so a bad email is explained next to the email box. The page
  // used to answer every refusal with "Check the name and try again", beside
  // the button -- which read as nothing happening when the email was the issue.
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const submitOnce = useSubmitOnce();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["referrals", "mine"],
    queryFn: fetchMyReferrals,
  });

  const add = useMutation({
    mutationFn: (payload: Record<Field, string>) => createReferral(payload),
    onSuccess: () => {
      setForm(EMPTY_FORM);
      setFieldErrors({});
      setError("");
      queryClient.invalidateQueries({ queryKey: ["referrals"] });
    },
    onError: (err: { response?: { data?: Record<string, unknown> } }) => {
      const data = err.response?.data ?? {};
      const onFields: Partial<Record<Field, string>> = {};
      for (const field of FIELDS) {
        const messages = data[field];
        if (Array.isArray(messages) && typeof messages[0] === "string") onFields[field] = messages[0];
      }
      setFieldErrors(onFields);
      setError(Object.keys(onFields).length ? "" : serverMessage(err, "Could not save that referral. Try again."));
    },
  });

  function update(field: Field, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
    // Editing a field is answering its refusal; stop showing it.
    setFieldErrors((current) => ({ ...current, [field]: undefined }));
  }

  function refer() {
    const payload = {
      name: form.name.trim(),
      phone: form.phone.trim(),
      email: form.email.trim(),
    };
    // Caught here to save a round trip; the server checks both again either way.
    const problems: Partial<Record<Field, string>> = {};
    if (payload.phone && !looksDialable(payload.phone)) problems.phone = NOT_A_PHONE;
    if (payload.email && !looksLikeEmail(payload.email)) problems.email = INVALID_EMAIL;
    if (Object.keys(problems).length) {
      setFieldErrors(problems);
      setError("");
      return;
    }
    // Once per click, however fast: a second request would raise a second
    // referral and a second call-back lead for the same person.
    submitOnce((settled) => add.mutate(payload, { onSettled: settled }));
  }

  async function copyCode() {
    if (!data?.code) return;
    try {
      await navigator.clipboard.writeText(data.code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard access can be refused; the code is on screen either way.
      setCopied(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Refer a Friend"
        subtitle="Bring someone in and get free days on your own membership."
      />

      {isLoading ? (
        <Card>
          <LoadingState />
        </Card>
      ) : isError || !data ? (
        <Card>
          <ErrorState />
        </Card>
      ) : (
        <>
          <div className="mb-6 grid gap-6 md:grid-cols-2">
            <Card accent={railColor(0)}>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                Your code
              </h2>
              <p className="mt-2 font-display text-5xl tracking-[0.2em] text-[var(--color-accent)]">
                {data.code}
              </p>
              <p className="mt-3 max-w-prose text-sm text-[var(--color-text-muted)]">
                {data.program_active
                  ? data.blurb ||
                    `Your friend enters this when they sign up. Once they join and pay, you get ${data.reward_days} free days.`
                  : "There is no referral offer running right now, but your code still tracks who you bring in."}
              </p>
              <div className="mt-4">
                <Button variant="secondary" onClick={copyCode}>
                  {copied ? "Copied" : "Copy code"}
                </Button>
              </div>
            </Card>

            <Card accent={railColor(3)}>
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                How you're doing
              </h2>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div>
                  <p className="font-display text-3xl leading-none text-[var(--color-text)]">
                    {data.total_referred}
                  </p>
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    Referred
                  </p>
                </div>
                <div>
                  <p className="font-display text-3xl leading-none text-[var(--color-text)]">
                    {data.joined_count}
                  </p>
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    Joined
                  </p>
                </div>
                <div>
                  <p className="font-display text-3xl leading-none text-[var(--color-accent)]">
                    {data.days_earned}
                  </p>
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-[var(--color-text-muted)]">
                    Free days
                  </p>
                </div>
              </div>
            </Card>
          </div>

          <Card accent={railColor(1)} className="mb-6">
            <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              Tell us who to call
            </h2>
            <p className="mb-4 text-sm text-[var(--color-text-muted)]">
              Leave a name and number and the front desk will ring them — you don't have to wait
              for them to use your code.
            </p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <Input
                  placeholder="Their name"
                  value={form.name}
                  onChange={(e) => update("name", e.target.value)}
                  aria-invalid={Boolean(fieldErrors.name)}
                  aria-describedby={fieldErrors.name ? "referral-name-error" : undefined}
                />
                <FieldError id="referral-name-error" message={fieldErrors.name} />
              </div>
              <div>
                <Input
                  placeholder="Phone (optional)"
                  value={form.phone}
                  onChange={(e) => update("phone", e.target.value)}
                  aria-invalid={Boolean(fieldErrors.phone)}
                  aria-describedby={fieldErrors.phone ? "referral-phone-error" : undefined}
                />
                <FieldError id="referral-phone-error" message={fieldErrors.phone} />
              </div>
              <div>
                <Input
                  type="email"
                  inputMode="email"
                  placeholder="Email (optional)"
                  value={form.email}
                  onChange={(e) => update("email", e.target.value)}
                  aria-invalid={Boolean(fieldErrors.email)}
                  aria-describedby={fieldErrors.email ? "referral-email-error" : undefined}
                />
                <FieldError id="referral-email-error" message={fieldErrors.email} />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={refer} disabled={!form.name.trim() || add.isPending}>
                {add.isPending ? "Saving..." : "Refer them"}
              </Button>
              <ErrorText>{error}</ErrorText>
            </div>
          </Card>

          <Card accent={railColor(2)}>
            <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
              People you've referred
            </h2>
            {!data.referrals.length ? (
              <EmptyState>Nobody yet. Share your code and it will show up here.</EmptyState>
            ) : (
              <div className="no-scrollbar overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-[var(--color-text-muted)]">
                    <tr className={tableHeadRowClass}>
                      <th className={tableHeadCellClass}>Name</th>
                      <th className={tableHeadCellClass}>Referred</th>
                      <th className={tableHeadCellClass}>Status</th>
                      <th className={tableHeadCellClass}>Your reward</th>
                    </tr>
                  </thead>
                  <motion.tbody initial="hidden" animate="visible" variants={staggerContainer(0.04)}>
                    {data.referrals.map((r) => (
                      <motion.tr key={r.id} variants={fadeUp} className={tableRowClass}>
                        <td className={tableCellClass}>{r.name}</td>
                        <td className={tableCellClass}>
                          {new Date(r.created_at).toLocaleDateString()}
                        </td>
                        <td className={tableCellClass}>
                          <span
                            className="rounded-full px-2.5 py-0.5 text-[11px] font-semibold"
                            style={{
                              background: `${STATUS_COLOR[r.status]}22`,
                              color: STATUS_COLOR[r.status],
                            }}
                          >
                            {STATUS_LABEL[r.status]}
                          </span>
                        </td>
                        <td className={tableCellClass}>
                          {r.reward
                            ? `${r.reward.days_granted} free days`
                            : r.is_rewardable
                              ? "Due — see the front desk"
                              : "-"}
                        </td>
                      </motion.tr>
                    ))}
                  </motion.tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
