import { useState } from "react";
import { statusColor } from "../../lib/theme";
import { Button, ghostButtonClass } from "../ui";

/**
 * Recovery codes, shown the one time they exist in readable form.
 *
 * The server keeps only their hashes, so there is no "show my codes" later. That
 * is why moving on waits until the person says they have saved them.
 */
export default function RecoveryCodes({
  codes,
  onDone,
  doneLabel = "Done",
}: {
  codes: string[];
  onDone: () => void;
  doneLabel?: string;
}) {
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);
  const text = codes.join("\n");

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function download() {
    const body =
      "Recovery codes\n\nEach one signs you in once, in place of a code from your " +
      `authenticator app.\n\n${text}\n`;
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "recovery-codes.txt";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-sm text-[var(--color-text-muted)]">
        If you lose your phone, each code signs you in once. Keep them somewhere that is not your
        phone, like a password manager or a printout.{" "}
        <b className="text-[var(--color-text)]">You will not see them again.</b>
      </p>
      <ul
        aria-label="Recovery codes"
        className="grid grid-cols-2 gap-x-6 gap-y-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-2)] p-4 font-mono text-sm text-[var(--color-text)]"
      >
        {codes.map((code) => (
          <li key={code}>{code}</li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={copy} className={ghostButtonClass}>
          {copied ? "Copied" : "Copy all"}
        </button>
        <button type="button" onClick={download} className={ghostButtonClass}>
          Download .txt
        </button>
      </div>
      <label className="flex items-center gap-2 text-sm text-[var(--color-text)]">
        <input
          type="checkbox"
          checked={saved}
          onChange={(e) => setSaved(e.target.checked)}
          className="h-4 w-4"
          style={{ accentColor: statusColor("positive") }}
        />
        I have saved these codes
      </label>
      <Button onClick={onDone} disabled={!saved} className="py-2.5">
        {doneLabel}
      </Button>
    </div>
  );
}
