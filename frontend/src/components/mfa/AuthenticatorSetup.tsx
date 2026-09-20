import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { MfaSetup } from "../../api/auth";
import { Button, ErrorText, ghostButtonClass } from "../ui";
import OneTimeCodeInput from "./OneTimeCodeInput";

const LABEL = "mb-1 block text-xs uppercase tracking-wide text-[var(--color-text-muted)]";

/** The key in fours, the way authenticator apps show it and people read it out. */
function grouped(secret: string) {
  return secret.match(/.{1,4}/g)?.join(" ") ?? secret;
}

/**
 * Adding this account to an authenticator app, then proving it worked.
 *
 * A QR code for when the app is on another device, the key written out for when
 * scanning is not an option, and a link that opens the app directly for someone
 * setting up on the phone in their hand -- a phone cannot scan its own screen.
 */
export default function AuthenticatorSetup({
  setup,
  onConfirm,
  pending,
  error,
  submitLabel = "Turn on",
  layout = "stacked",
}: {
  setup: MfaSetup;
  onConfirm: (code: string) => void;
  pending: boolean;
  error: string;
  submitLabel?: string;
  /** `side` puts the key beside the QR code, for a wide card. */
  layout?: "stacked" | "side";
}) {
  const [image, setImage] = useState("");
  const [code, setCode] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Dark on white whatever the theme: phone cameras give up on a tinted code.
    QRCode.toDataURL(setup.otpauth_uri, {
      width: 320,
      margin: 1,
      errorCorrectionLevel: "M",
      color: { dark: "#000000", light: "#ffffff" },
    })
      .then((url) => {
        if (!cancelled) setImage(url);
      })
      .catch(() => {
        if (!cancelled) setImage("");
      });
    return () => {
      cancelled = true;
    };
  }, [setup.otpauth_uri]);

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(setup.secret);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  const side = layout === "side";

  return (
    <div className="flex flex-col gap-5">
      <ol className="flex list-decimal flex-col gap-1 pl-5 text-sm text-[var(--color-text-muted)]">
        <li>
          Open an authenticator app, such as Google Authenticator, Microsoft Authenticator or
          1Password.
        </li>
        <li>Scan this code, or type in the key.</li>
        <li>Enter the 6-digit code the app shows.</li>
      </ol>

      <div className={`flex flex-col items-center gap-4 ${side ? "sm:flex-row sm:items-start" : ""}`}>
        {image ? (
          <img
            src={image}
            alt="QR code for adding this account to an authenticator app"
            width={160}
            height={160}
            className="h-40 w-40 shrink-0 rounded-lg bg-white p-2"
          />
        ) : (
          <div
            className="h-40 w-40 shrink-0 animate-pulse rounded-lg bg-[var(--color-surface-2)]"
            aria-hidden="true"
          />
        )}
        <div className={`min-w-0 text-sm ${side ? "w-full sm:flex-1" : "w-full"}`}>
          <p className={LABEL}>Key</p>
          <p className="break-all font-mono text-[var(--color-text)]">{grouped(setup.secret)}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <button type="button" onClick={copyKey} className={ghostButtonClass}>
              {copied ? "Copied" : "Copy key"}
            </button>
            {/* Opens the authenticator on a phone. On a desktop there is usually
                nothing registered to open it, so it is hidden there. */}
            <a href={setup.otpauth_uri} className={`${ghostButtonClass} lg:hidden`}>
              Open in app
            </a>
          </div>
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            The app lists it as {setup.issuer} ({setup.account_name}).
          </p>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(code);
          setCode("");
        }}
        className="flex flex-col gap-3"
      >
        <div>
          <label htmlFor="mfa-setup-code" className={LABEL}>
            Code from the app
          </label>
          <OneTimeCodeInput id="mfa-setup-code" value={code} onChange={setCode} />
        </div>
        <ErrorText>{error}</ErrorText>
        <Button type="submit" disabled={pending || code.length !== 6} className="py-2.5">
          {pending ? "Checking..." : submitLabel}
        </Button>
      </form>
    </div>
  );
}
