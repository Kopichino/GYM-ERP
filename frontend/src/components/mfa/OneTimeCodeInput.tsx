import { Input } from "../ui";

/**
 * Six digits from an authenticator app.
 *
 * `one-time-code` lets a phone offer the code itself, and `numeric` opens the
 * number pad. Anything that is not a digit is dropped as it is typed, so a code
 * pasted as "123 456" still fits -- which is also why there is no `maxLength`:
 * the browser would cut that paste off before the spaces were stripped.
 */
export default function OneTimeCodeInput({
  id,
  value,
  onChange,
  autoFocus,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  autoFocus?: boolean;
}) {
  return (
    <Input
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value.replace(/\D/g, "").slice(0, 6))}
      inputMode="numeric"
      autoComplete="one-time-code"
      autoFocus={autoFocus}
      required
      className="h-12 text-center font-mono text-2xl tracking-[0.4em]"
    />
  );
}
