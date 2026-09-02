import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  PropsWithChildren,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function Card({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  return (
    <div
      className={`rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition-colors duration-200 hover:border-[var(--color-border)]/80 ${className}`}
    >
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mb-6">
      <div className="mb-2 h-1 w-10 rounded-full bg-[var(--color-accent)]" />
      <h1 className="font-display text-4xl uppercase tracking-wide text-[var(--color-text)] sm:text-5xl">
        {title}
      </h1>
      {subtitle && <p className="mt-1 text-sm text-[var(--color-text-muted)]">{subtitle}</p>}
    </div>
  );
}

type Variant = "primary" | "secondary" | "danger";

const variantClasses: Record<Variant, string> = {
  primary: "bg-[var(--color-accent)] text-white hover:opacity-90",
  secondary:
    "border border-[var(--color-border)] text-[var(--color-text)] hover:border-[var(--color-accent)]",
  danger: "bg-red-600 text-white hover:opacity-90",
};

type ButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onAnimationStart" | "onAnimationEnd" | "onDrag" | "onDragStart" | "onDragEnd"
> & { variant?: Variant };

export function Button({ variant = "primary", className = "", disabled, ...props }: ButtonProps) {
  return (
    <motion.button
      whileHover={disabled ? undefined : { scale: 1.03 }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.15 }}
      disabled={disabled}
      className={`rounded-md px-4 py-2 text-sm font-semibold transition-opacity disabled:cursor-not-allowed disabled:opacity-50 ${variantClasses[variant]} ${className}`}
      {...props}
    />
  );
}

export function ErrorText({ children }: PropsWithChildren) {
  if (!children) return null;
  return <p className="text-sm text-red-400">{children}</p>;
}

const fieldClass =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={`${fieldClass} ${props.className ?? ""}`} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`${fieldClass} ${props.className ?? ""}`} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={`${fieldClass} ${props.className ?? ""}`} />;
}

/** Shared loading/empty/error states so every list/table reads consistently
 * instead of silently showing nothing while a query is in flight or failed. */
export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-6 text-sm text-[var(--color-text-muted)]">
      <motion.span
        className="h-2 w-2 rounded-full bg-[var(--color-accent)]"
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      />
      {label}
    </div>
  );
}

export function EmptyState({ children }: PropsWithChildren) {
  return <p className="py-6 text-sm text-[var(--color-text-muted)]">{children}</p>;
}

export function ErrorState({ children = "Something went wrong. Please try again." }: PropsWithChildren) {
  return <p className="py-6 text-sm text-red-400">{children}</p>;
}

/** Animates from its previous value to `value` whenever it changes -- the
 * same easing curve LandingPage's stat counters use, factored out so any
 * stat (billing days-remaining, streak counts, ...) can reuse it. */
export function AnimatedNumber({ value, duration = 700 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(value);
  const prev = useRef(value);

  useEffect(() => {
    if (prev.current === value) {
      setDisplay(value);
      return;
    }
    const from = prev.current;
    const to = value;
    prev.current = value;
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      setDisplay(Math.round(from + (to - from) * (1 - Math.pow(1 - t, 3))));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [value, duration]);

  return <span>{display}</span>;
}

/** Shared table styling so admin data tables (Members, Billing, ...) match. */
export const tableHeadRowClass = "border-b border-[var(--color-border)]";
export const tableHeadCellClass = "py-2 pr-4";
export const tableRowClass = "border-b border-[var(--color-border)] text-[var(--color-text)] last:border-none";
export const tableCellClass = "py-2 pr-4";
