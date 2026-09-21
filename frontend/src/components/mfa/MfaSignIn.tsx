import { useEffect, useState } from "react";
import {
  confirmSignInMfaSetup,
  startSignInMfaSetup,
  verifyMfa,
  type MfaSetup,
} from "../../api/auth";
import { statusColor } from "../../lib/theme";
import AuthLayout from "../layout/AuthLayout";
import { Button, ErrorText, Input } from "../ui";
import AuthenticatorSetup from "./AuthenticatorSetup";
import { mfaErrorMessage, mfaReason } from "./mfaErrors";
import OneTimeCodeInput from "./OneTimeCodeInput";
import RecoveryCodes from "./RecoveryCodes";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";
const LINK = "self-start text-sm font-semibold text-[var(--color-accent)] hover:underline";

/** What the password step handed over: a code is due, or setting one up is. */
export interface PendingSignIn {
  kind: "mfa" | "mfa_setup";
  mfaToken: string;
}

type Step = "code" | "recovery" | "setup" | "codes" | "recovered";

const COPY: Record<Step, { title: string; subtitle: string }> = {
  code: {
    title: "Enter your code",
    subtitle: "Open your authenticator app and type the 6-digit code it shows for this account.",
  },
  recovery: {
    title: "Use a recovery code",
    subtitle: "Type one of the recovery codes you saved when you set up two-step sign-in.",
  },
  setup: {
    title: "Set up two-step sign-in",
    subtitle:
      "Every account signs in with a code from an authenticator app as well as a password. It takes about a minute.",
  },
  codes: {
    title: "Save your recovery codes",
    subtitle: "Two-step sign-in is on. One more thing before you go in.",
  },
  recovered: { title: "Recovery code used", subtitle: "You are signed in." },
};

/**
 * The second half of signing in, after a correct password.
 *
 * Shared by the login and signup pages. A new account meets the setup step
 * straight after it is created; after that, it is the code step every time.
 */
export default function MfaSignIn({
  pending,
  onSignedIn,
  onRestart,
}: {
  pending: PendingSignIn;
  onSignedIn: (access: string) => Promise<void>;
  /** Back to the password, with a reason to show there if there is one. */
  onRestart: (message?: string) => void;
}) {
  const [step, setStep] = useState<Step>(pending.kind === "mfa_setup" ? "setup" : "code");
  const [code, setCode] = useState("");
  const [recoveryCode, setRecoveryCode] = useState("");
  const [setup, setSetup] = useState<MfaSetup | null>(null);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [remaining, setRemaining] = useState(0);
  // Held while the recovery codes or the running-low notice are on screen: the
  // session is already open by then, and going in waits on the person.
  const [access, setAccess] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function fail(err: unknown, fallback: string) {
    const reason = mfaReason(err);
    if (reason === "mfa_token_invalid") {
      onRestart("That took too long, so the sign-in expired. Enter your password again.");
    } else if (reason === "mfa_already_set_up") {
      setError("");
      setStep("code");
    } else if (reason === "mfa_setup_required") {
      setError("");
      setStep("setup");
    } else {
      setError(mfaErrorMessage(err, fallback));
    }
  }

  useEffect(() => {
    if (step !== "setup" || setup) return;
    let cancelled = false;
    // The server hands back the same key if this runs twice, so a development
    // double-render or a quick back-and-forth cannot swap the QR code under
    // someone who has already scanned it.
    startSignInMfaSetup(pending.mfaToken)
      .then((data) => {
        if (!cancelled) setSetup(data);
      })
      .catch((err) => {
        if (!cancelled) fail(err, "Could not start setting up two-step sign-in.");
      });
    return () => {
      cancelled = true;
    };
    // `fail` is recreated every render and only reads setters and props.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, setup, pending.mfaToken]);

  async function run(action: () => Promise<void>, fallback: string) {
    setError("");
    setBusy(true);
    try {
      await action();
    } catch (err) {
      fail(err, fallback);
    } finally {
      setBusy(false);
    }
  }

  function submitCode(e: React.FormEvent) {
    e.preventDefault();
    void run(async () => {
      try {
        const data = await verifyMfa({ mfa_token: pending.mfaToken, code });
        await onSignedIn(data.access);
      } catch (err) {
        // A new code is along in seconds, and the old one is no use to retype.
        setCode("");
        throw err;
      }
    }, "Could not check that code.");
  }

  function submitRecoveryCode(e: React.FormEvent) {
    e.preventDefault();
    void run(async () => {
      const data = await verifyMfa({ mfa_token: pending.mfaToken, recovery_code: recoveryCode });
      // Always a stop on the way in: using one usually means the phone is gone,
      // and this is the moment to say what to do about it.
      setAccess(data.access);
      setRemaining(data.recovery_codes_remaining ?? 0);
      setStep("recovered");
    }, "Could not check that recovery code.");
  }

  function confirmSetup(value: string) {
    void run(async () => {
      const data = await confirmSignInMfaSetup(pending.mfaToken, value);
      setAccess(data.access);
      setRecoveryCodes(data.recovery_codes);
      setStep("codes");
    }, "Could not check that code.");
  }

  function goIn() {
    void run(() => onSignedIn(access), "Signed in, but the app could not load. Reload the page.");
  }

  const signedIn = step === "codes" || step === "recovered";
  const footer = signedIn ? null : (
    <>
      Wrong account?{" "}
      <button
        type="button"
        onClick={() => onRestart()}
        className="font-semibold text-[var(--color-accent)] hover:underline"
      >
        Start again
      </button>
    </>
  );

  return (
    <AuthLayout variant="login" title={COPY[step].title} subtitle={COPY[step].subtitle} footer={footer}>
      {step === "code" && (
        <form onSubmit={submitCode} className="flex flex-col gap-3">
          <div>
            <label htmlFor="mfa-code" className={LABEL}>
              6-digit code
            </label>
            <OneTimeCodeInput id="mfa-code" value={code} onChange={setCode} autoFocus />
          </div>
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={busy || code.length !== 6} className="mt-2 py-2.5">
            {busy ? "Checking..." : "Sign in"}
          </Button>
          <button
            type="button"
            onClick={() => {
              setError("");
              setStep("recovery");
            }}
            className={LINK}
          >
            Lost your phone? Use a recovery code
          </button>
        </form>
      )}

      {step === "recovery" && (
        <form onSubmit={submitRecoveryCode} className="flex flex-col gap-3">
          <div>
            <label htmlFor="mfa-recovery" className={LABEL}>
              Recovery code
            </label>
            <Input
              id="mfa-recovery"
              value={recoveryCode}
              onChange={(e) => setRecoveryCode(e.target.value)}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              autoFocus
              required
              className="h-12 font-mono text-lg"
            />
          </div>
          <ErrorText>{error}</ErrorText>
          <Button type="submit" disabled={busy || !recoveryCode.trim()} className="mt-2 py-2.5">
            {busy ? "Checking..." : "Sign in"}
          </Button>
          <button
            type="button"
            onClick={() => {
              setError("");
              setStep("code");
            }}
            className={LINK}
          >
            Use a code from the app instead
          </button>
          <p className="text-xs text-[var(--color-text-muted)]">
            No recovery codes either? Ask the gym to reset two-step sign-in on your account.
          </p>
        </form>
      )}

      {step === "setup" &&
        (setup ? (
          <AuthenticatorSetup
            setup={setup}
            onConfirm={confirmSetup}
            pending={busy}
            error={error}
            submitLabel="Turn on and sign in"
          />
        ) : error ? (
          <ErrorText>{error}</ErrorText>
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">Preparing your key...</p>
        ))}

      {step === "codes" && (
        <div className="flex flex-col gap-3">
          <RecoveryCodes codes={recoveryCodes} onDone={goIn} doneLabel="Continue" />
          <ErrorText>{error}</ErrorText>
        </div>
      )}

      {step === "recovered" && (
        <div className="flex flex-col gap-4 text-sm text-[var(--color-text-muted)]">
          <p>
            <b style={{ color: remaining <= 3 ? statusColor("caution") : "var(--color-text)" }}>
              {remaining} recovery {remaining === 1 ? "code" : "codes"} left.
            </b>{" "}
            If you have lost your phone, go to your profile (My Account for admins) and choose{" "}
            <b className="text-[var(--color-text)]">Move to a new phone</b>. That also gives you a
            fresh set of codes.
          </p>
          <ErrorText>{error}</ErrorText>
          <Button onClick={goIn} disabled={busy} className="py-2.5">
            Continue
          </Button>
        </div>
      )}
    </AuthLayout>
  );
}
