import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  confirmMfaSetup,
  fetchMfaStatus,
  regenerateRecoveryCodes,
  startMfaSetup,
  type MfaSetup,
} from "../api/auth";
import { statusColor, tint } from "../lib/theme";
import { useAuthStore } from "../store/authStore";
import AuthenticatorSetup from "./mfa/AuthenticatorSetup";
import { mfaErrorMessage } from "./mfa/mfaErrors";
import OneTimeCodeInput from "./mfa/OneTimeCodeInput";
import RecoveryCodes from "./mfa/RecoveryCodes";
import { Button, Card, ErrorState, ErrorText, Input, LoadingState } from "./ui";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";
const PILL = "inline-block rounded-full px-2 py-1 text-[11px] font-semibold leading-none";
const STATUS_KEY = ["auth", "mfa-status"];

type Panel = "idle" | "password" | "setup" | "code" | "codes";

/**
 * Two-step sign-in, from your own profile.
 *
 * Two jobs. A fresh set of recovery codes, for a current code from the app. And
 * moving to a new phone, for the password -- the same bar as changing it,
 * because a stolen session should not be able to swap the authenticator out
 * from under the real owner. There is no "turn off": every account uses it.
 */
export default function MfaCard() {
  const queryClient = useQueryClient();
  const { data: status, isLoading, isError } = useQuery({
    queryKey: STATUS_KEY,
    queryFn: fetchMfaStatus,
  });
  const [panel, setPanel] = useState<Panel>("idle");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [codes, setCodes] = useState<string[]>([]);
  const [error, setError] = useState("");

  function open(next: Panel) {
    setError("");
    setPassword("");
    setCode("");
    setPanel(next);
  }

  function close() {
    open("idle");
    setSetup(null);
    setCodes([]);
    queryClient.invalidateQueries({ queryKey: STATUS_KEY });
  }

  const begin = useMutation({
    mutationFn: () => startMfaSetup(password),
    onSuccess: (data) => {
      setSetup(data);
      setPassword("");
      setError("");
      setPanel("setup");
    },
    onError: (err) => setError(mfaErrorMessage(err, "Could not start moving to a new phone.")),
  });

  const confirm = useMutation({
    mutationFn: (value: string) => confirmMfaSetup(value),
    onSuccess: (data) => {
      // Every other session was ended and this one re-issued.
      useAuthStore.getState().setAccessToken(data.access);
      setCodes(data.recovery_codes);
      setSetup(null);
      setError("");
      setPanel("codes");
    },
    onError: (err) => setError(mfaErrorMessage(err, "Could not check that code.")),
  });

  const regenerate = useMutation({
    mutationFn: () => regenerateRecoveryCodes(code),
    onSuccess: (data) => {
      setCodes(data.recovery_codes);
      setCode("");
      setError("");
      setPanel("codes");
    },
    onError: (err) => {
      setCode("");
      setError(mfaErrorMessage(err, "Could not make new recovery codes."));
    },
  });

  const remaining = status?.recovery_codes_remaining ?? 0;
  const low = remaining <= 3;
  const tone = statusColor(status?.enabled ? "positive" : "caution");

  let body;
  if (isLoading) {
    body = <LoadingState />;
  } else if (isError || !status) {
    body = <ErrorState />;
  } else if (panel === "password") {
    body = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          begin.mutate();
        }}
        className="grid max-w-md gap-3"
      >
        <p className="text-sm text-[var(--color-text-muted)]">
          Your current authenticator keeps working until the new phone is confirmed. Enter your
          password to start.
        </p>
        <div>
          <label htmlFor="mfa-password" className={LABEL}>
            Current password
          </label>
          <Input
            id="mfa-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <ErrorText>{error}</ErrorText>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={!password || begin.isPending}>
            {begin.isPending ? "Checking..." : "Continue"}
          </Button>
          <Button type="button" variant="secondary" onClick={close}>
            Cancel
          </Button>
        </div>
      </form>
    );
  } else if (panel === "setup" && setup) {
    body = (
      <div className="flex max-w-xl flex-col gap-3">
        <AuthenticatorSetup
          setup={setup}
          layout="side"
          onConfirm={(value) => confirm.mutate(value)}
          pending={confirm.isPending}
          error={error}
          submitLabel="Use this phone"
        />
        <Button type="button" variant="secondary" onClick={close} className="self-start">
          Cancel
        </Button>
      </div>
    );
  } else if (panel === "code") {
    body = (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          regenerate.mutate();
        }}
        className="grid max-w-md gap-3"
      >
        <p className="text-sm text-[var(--color-text-muted)]">
          Your old recovery codes stop working as soon as the new ones are made.
        </p>
        <div>
          <label htmlFor="mfa-regenerate-code" className={LABEL}>
            Code from your authenticator app
          </label>
          <OneTimeCodeInput id="mfa-regenerate-code" value={code} onChange={setCode} />
        </div>
        <ErrorText>{error}</ErrorText>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={code.length !== 6 || regenerate.isPending}>
            {regenerate.isPending ? "Checking..." : "Make new codes"}
          </Button>
          <Button type="button" variant="secondary" onClick={close}>
            Cancel
          </Button>
        </div>
      </form>
    );
  } else if (panel === "codes") {
    body = (
      <div className="max-w-md">
        <RecoveryCodes codes={codes} onDone={close} />
      </div>
    );
  } else {
    body = (
      <div className="flex flex-col gap-4">
        {status.enabled ? (
          <dl className="grid gap-4 text-sm sm:grid-cols-2">
            <div>
              <dt className={LABEL}>Set up on</dt>
              <dd className="text-[var(--color-text)]">
                {status.confirmed_at ? new Date(status.confirmed_at).toLocaleDateString() : "-"}
              </dd>
            </div>
            <div>
              <dt className={LABEL}>Recovery codes left</dt>
              <dd
                className={low ? "font-semibold" : "text-[var(--color-text)]"}
                style={low ? { color: statusColor("caution") } : undefined}
              >
                {remaining} of 10{low ? ". Make new ones soon." : ""}
              </dd>
            </div>
          </dl>
        ) : (
          <p className="text-sm text-[var(--color-text)]">Not set up on this account yet.</p>
        )}
        <div className="flex flex-wrap gap-2">
          {status.enabled && (
            <Button variant="secondary" onClick={() => open("code")}>
              New recovery codes
            </Button>
          )}
          <Button variant="secondary" onClick={() => open("password")}>
            {status.enabled ? "Move to a new phone" : "Set up"}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <Card accent={tone}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
          Two-step sign-in
        </h2>
        {status && (
          <span className={PILL} style={{ color: tone, background: tint(tone) }}>
            {status.enabled ? "On" : "Off"}
          </span>
        )}
      </div>
      <p className="mb-4 max-w-prose text-sm text-[var(--color-text-muted)]">
        You sign in with your password and a code from your authenticator app, so a stolen password
        is not enough on its own.
      </p>
      {body}
    </Card>
  );
}
