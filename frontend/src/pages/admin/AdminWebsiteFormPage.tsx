import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  createLeadKey,
  deleteLeadKey,
  fetchLeadKeys,
  LEAD_FAILURE_HELP,
  revokeLeadKey,
  type LeadApiKey,
  type LeadFailureReason,
} from "../../api/leadKeys";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  ErrorText,
  ghostButtonClass,
  Input,
  LoadingState,
  Textarea,
} from "../../components/ui";
import { absoluteUrl } from "../../lib/api";
import { statusColor, tint } from "../../lib/theme";
import { askConfirm } from "../../store/confirmStore";

const ENDPOINT = absoluteUrl("/tenancy/leads/");

/** Has to match the server's `HONEYPOT_FIELD` in `tenancy/leads.py`. */
const HONEYPOT = "company_website";

function snippetFor(key: string) {
  return [
    '<form id="gym-enquiry">',
    '  <input name="name" placeholder="Your name" required>',
    '  <input name="phone" placeholder="Phone number">',
    '  <input name="email" placeholder="Email">',
    '  <textarea name="message" placeholder="What are you looking for?"></textarea>',
    "",
    "  <!-- Leave this hidden. Bots fill it in; people cannot see it. -->",
    `  <input name="${HONEYPOT}" style="display:none" tabindex="-1" autocomplete="off">`,
    "",
    '  <button type="submit">Send</button>',
    "</form>",
    "",
    "<script>",
    'document.getElementById("gym-enquiry").addEventListener("submit", async (e) => {',
    "  e.preventDefault();",
    "  const form = e.target;",
    "",
    "  // One reusable line, so submitting again replaces the message rather",
    "  // than stacking another copy of it under the button.",
    "  const say = (text) => {",
    '    let note = form.querySelector(".enquiry-note");',
    "    if (!note) {",
    '      note = document.createElement("p");',
    '      note.className = "enquiry-note";',
    "      form.appendChild(note);",
    "    }",
    "    note.textContent = text;",
    "  };",
    "",
    "  try {",
    `    const res = await fetch("${ENDPOINT}", {`,
    '      method: "POST",',
    `      headers: { "Content-Type": "application/json", "X-Lead-Key": "${key}" },`,
    "      body: JSON.stringify(Object.fromEntries(new FormData(form))),",
    "    });",
    "",
    "    // A 4xx or 5xx is a *successful* fetch -- the reply arrived, it just",
    "    // said no. Without this check a refused enquiry would be thanked",
    "    // exactly like an accepted one, and nobody would ever chase it.",
    "    if (res.ok) {",
    '      form.textContent = "Thanks, we will be in touch.";',
    "    } else if (res.status === 400) {",
    "      // The only failure the visitor can actually fix themselves.",
    '      say("Please add your name and either a phone number or an email.");',
    "    } else {",
    "      // 401 revoked key, 429 too many, 5xx our end. Not their fault and",
    "      // not their problem to solve, so send them somewhere that works.",
    '      say("Sorry, we could not accept that just now - please call us.");',
    "    }",
    "  } catch (err) {",
    "    // Only a genuine network failure lands here: no connection, DNS, CORS.",
    '    say("That did not send. Please check your connection and try again.");',
    "  }",
    "});",
    "</script>",
  ].join("\n");
}

function CopyButton({ value, label = "Copy" }: { value: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      className={ghostButtonClass}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Blocked in some contexts. The value is on screen and selectable, so
          // this is not worth an error message.
        }
      }}
    >
      {copied ? "Copied" : label}
    </button>
  );
}

/**
 * The key, shown once.
 *
 * The server keeps only a hash, so this panel is the single moment the
 * plaintext exists anywhere an owner can reach it. It stays on screen until
 * they dismiss it rather than vanishing on the next render, and it says plainly
 * that it will not come back -- an owner who closes it and then goes looking
 * for it is the failure this wording exists to prevent.
 */
function NewKeyPanel({ value, onDone }: { value: string; onDone: () => void }) {
  const snippet = snippetFor(value);

  return (
    <Card accent={statusColor("caution")} className="mb-6">
      <h2
        className="mb-1 text-sm font-semibold uppercase tracking-wide"
        style={{ color: statusColor("caution") }}
      >
        Copy this now, it is not shown again
      </h2>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        We store a scrambled copy rather than the key itself, so nobody here can
        look it up for you later. If you lose it, issue a new one and swap it on
        your site &mdash; the old one keeps working until you revoke it.
      </p>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)]">
          {value}
        </code>
        <CopyButton value={value} label="Copy key" />
      </div>

      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-[var(--color-text)]">
          Paste this into your website where the contact form should appear.
        </p>
        <CopyButton value={snippet} label="Copy the form code" />
      </div>
      {/* scroll-thin: without it the code block gets the browser's default
          scrollbars, which render light and are the only white thing on a dark
          page. */}
      <pre className="scroll-thin max-h-64 overflow-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] p-3 text-xs leading-relaxed text-[var(--color-text-muted)]">
        {snippet}
      </pre>

      <Button variant="success" className="mt-4" onClick={onDone}>
        I have copied it
      </Button>
    </Card>
  );
}

/** Active keys that are currently failing. A revoked key is not a fault. */
function broken(keys: LeadApiKey[] | undefined) {
  return (keys ?? []).filter(
    (k) => k.is_active && k.failures_since_success > 0 && k.last_failure_reason,
  );
}

function since(value: string | null) {
  if (!value) return "";
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000);
  if (days >= 1) return ` — and has been since ${new Date(value).toLocaleDateString()}`;
  return " — most recently in the last day";
}

/**
 * The whole point of tracking failures.
 *
 * A form that breaks on someone else's website breaks silently here: the
 * visitor gets an apology and the gym gets nothing, so the fault is normally
 * discovered weeks later by noticing enquiries have dried up. This says it on
 * the day it happens, in the words of the person who has to fix it.
 *
 * Red rather than amber: enquiries are being lost right now, which is not a
 * "look at this when you can".
 */
function FailureBanner({ keys }: { keys: LeadApiKey[] }) {
  return (
    <Card accent={statusColor("negative")} className="mb-6">
      <h2
        className="mb-1 text-sm font-semibold uppercase tracking-wide"
        style={{ color: statusColor("negative") }}
      >
        {keys.length === 1
          ? "Your website form is not working"
          : `${keys.length} website forms are not working`}
      </h2>
      <div className="flex flex-col gap-3">
        {keys.map((item) => {
          const help = LEAD_FAILURE_HELP[item.last_failure_reason as LeadFailureReason];
          return (
            <div key={item.id}>
              <p className="text-sm text-[var(--color-text)]">
                <b>{help.headline}</b>
                <span className="text-[var(--color-text-muted)]">
                  {since(item.last_failure_at)}
                </span>
              </p>
              <p className="mt-1 max-w-prose text-sm text-[var(--color-text-muted)]">
                {help.advice}
              </p>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                Key: {item.label}
              </p>
            </div>
          );
        })}
      </div>
      <p className="mt-4 max-w-prose text-xs text-[var(--color-text-muted)]">
        This clears itself as soon as one enquiry gets through, so you do not
        need to dismiss it — fix the form and it will go.
      </p>
    </Card>
  );
}

function when(value: string | null) {
  return value ? new Date(value).toLocaleDateString() : "never";
}

function KeyRow({ item }: { item: LeadApiKey }) {
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lead-keys"] });

  const revoke = useMutation({
    mutationFn: () => revokeLeadKey(item.id),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: () => deleteLeadKey(item.id),
    onSuccess: invalidate,
  });

  const origins = item.allowed_origins
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  const tone = item.is_active ? statusColor("positive") : statusColor("negative");

  return (
    <li className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--color-border)] py-3 last:border-none">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-semibold text-[var(--color-text)]">{item.label}</p>
          <span
            className="inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none"
            style={{ color: tone, background: tint(tone) }}
          >
            {item.is_active ? "Active" : "Revoked"}
          </span>
        </div>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {item.leads_created} {item.leads_created === 1 ? "enquiry" : "enquiries"} &middot;
          last used {when(item.last_used_at)} &middot; added {when(item.created_at)}
        </p>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {origins.length ? `Only from ${origins.join(", ")}` : "Works from any website"}
        </p>
      </div>

      {/* A revoked key is kept for its usage history; removing it throws that
          away. Two separate actions rather than one button that quietly does
          both, so an owner stopping a leak does not also lose the record of
          what it sent. */}
      <div className="flex flex-wrap gap-2">
        {item.is_active ? (
          <Button
            variant="danger"
            className="px-3 py-1 text-xs"
            disabled={revoke.isPending}
            onClick={() =>
              askConfirm({
                title: `Revoke "${item.label}"?`,
                consequence:
                  "Your website stops being able to send enquiries the moment this is revoked. Enquiries already in your pipeline are not affected.",
                confirmLabel: "Revoke",
                run: () => revoke.mutate(),
              })
            }
          >
            Revoke
          </Button>
        ) : (
          <Button
            variant="danger"
            className="px-3 py-1 text-xs"
            disabled={remove.isPending}
            onClick={() =>
              askConfirm({
                title: `Delete "${item.label}"?`,
                consequence: `The record of the ${item.leads_created} enquiries it sent goes with it.`,
                confirmLabel: "Delete",
                run: () => remove.mutate(),
              })
            }
          >
            Delete
          </Button>
        )}
      </div>
    </li>
  );
}

export default function AdminWebsiteFormPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ label: "", allowed_origins: "" });
  const [issued, setIssued] = useState<string | null>(null);
  const [error, setError] = useState("");

  const { data: keys, isLoading, isError } = useQuery({
    queryKey: ["lead-keys"],
    queryFn: fetchLeadKeys,
  });

  const faults = broken(keys);

  const create = useMutation({
    mutationFn: () => createLeadKey(form),
    onSuccess: (key) => {
      setError("");
      setForm({ label: "", allowed_origins: "" });
      setIssued(key.plaintext ?? null);
      queryClient.invalidateQueries({ queryKey: ["lead-keys"] });
    },
    onError: (err: { response?: { data?: Record<string, unknown> } }) => {
      const first = err.response?.data && Object.values(err.response.data)[0];
      setError(
        String(Array.isArray(first) ? first[0] : (first ?? "Could not issue a key.")),
      );
    },
  });

  return (
    <div>
      {faults.length > 0 && <FailureBanner keys={faults} />}
      {issued && <NewKeyPanel value={issued} onDone={() => setIssued(null)} />}

      <Card accent={statusColor("neutral")} className="mb-6">
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Take enquiries from your own website
        </h2>
        <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
          Put a contact form on your site and the people who fill it in land
          straight in your Enquiries pipeline, with no copying from an inbox.
          Issue a key below and we will give you the form code to paste in.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label
              htmlFor="key-label"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              What is it for?
            </label>
            <Input
              id="key-label"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              placeholder="Main website contact form"
            />
          </div>
          <div>
            <label
              htmlFor="key-origins"
              className="mb-1 block text-xs text-[var(--color-text-muted)]"
            >
              Only accept from these addresses (optional)
            </label>
            <Textarea
              id="key-origins"
              rows={2}
              value={form.allowed_origins}
              onChange={(e) =>
                setForm((f) => ({ ...f, allowed_origins: e.target.value }))
              }
              placeholder={"https://www.yourgym.com\nhttps://yourgym.com"}
            />
            {/* Said plainly, because the honest advice is "usually leave this
                blank": a form posted from a server sends no Origin at all, and
                an owner who fills this in on a whim gets silent refusals from a
                key that looks perfectly correct. */}
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              One per line. Leave blank unless you know your form runs in a
              browser on these exact addresses.
            </p>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <Button
            onClick={() => create.mutate()}
            disabled={!form.label.trim() || create.isPending}
          >
            {create.isPending ? "Issuing..." : "Issue a key"}
          </Button>
          <ErrorText>{error}</ErrorText>
        </div>
      </Card>

      <Card accent={statusColor("neutral")}>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Your keys
        </h2>
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState />
        ) : !keys?.length ? (
          <EmptyState>
            No keys yet, so your website is not sending enquiries here.
          </EmptyState>
        ) : (
          <ul className="flex flex-col">
            {keys.map((item) => (
              <KeyRow key={item.id} item={item} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
