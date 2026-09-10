import { motion } from "framer-motion";
import {
  Children,
  isValidElement,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import type {
  ButtonHTMLAttributes,
  Ref,
  CSSProperties,
  InputHTMLAttributes,
  PropsWithChildren,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

/**
 * Every panel carries a coloured rail along its top edge. `accent` sets it --
 * pass a semantic colour where the panel already means something (a role, a
 * status, a muscle group) and let it cycle everywhere else, so colour stays
 * informative rather than decorative.
 */
export function Card({
  children,
  className = "",
  style,
  accent,
}: PropsWithChildren<{ className?: string; style?: CSSProperties; accent?: string }>) {
  return (
    <div
      style={{ borderTopColor: accent ?? "var(--color-accent)", ...style }}
      className={`rounded-xl border border-t-[3px] border-[var(--color-border)] bg-[var(--color-surface)] p-5 transition-colors duration-200 ${className}`}
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

/**
 * What a button *does*, not what colour someone wanted.
 *
 * `primary` used to be the brand accent -- which is red -- so the default
 * button and the destructive button were two shades of the same colour, and
 * 103 of the app's 147 buttons were red. "Mark called" looked exactly as
 * dangerous as "Delete". Red now means one thing.
 *
 * - `primary`   the main way forward on a screen: Save, Create, Add.
 * - `success`   completes or resolves something: Mark called, Mark paid, Done.
 * - `secondary` everything else. The quiet default; most buttons want this.
 * - `danger`    destroys data. Nothing else may use it.
 */
type Variant = "primary" | "secondary" | "success" | "danger";

const variantClasses: Record<Variant, string> = {
  // Brand crimson, kept for the single main action on a screen. It reads as
  // emphasis rather than danger precisely because it is now rare.
  primary: "bg-[var(--color-accent)] text-white hover:opacity-90",
  secondary:
    "border border-[var(--color-border)] text-[var(--color-text)] hover:border-[var(--color-accent)]",
  success: "bg-[#22c55e] text-white hover:opacity-90",
  danger: "bg-red-600 text-white hover:opacity-90",
};

/**
 * How a button looks while it is waiting on something.
 *
 * Dashed, and tinted with the button's *own* colour rather than a flat grey --
 * so it previews what it is about to become. A disabled "Create badge" hints
 * crimson, a disabled "Mark called" hints green. The alpha is deliberately low
 * (roughly 40% on the border, 60% on the label): enough to carry the meaning,
 * not enough to be mistaken for the live button.
 *
 * A faded version of the *solid* fill was what made "Create badge" look broken;
 * the dashes are what say "not yet", and the tint is only there to say which
 * button it is.
 */
const disabledClasses: Record<Variant, string> = {
  primary: "border border-dashed border-[#ff3d5a66] bg-[#ff3d5a0d] text-[#ff3d5a99]",
  secondary:
    "border border-dashed border-[#9494a866] bg-transparent text-[#9494a8cc]",
  success: "border border-dashed border-[#22c55e66] bg-[#22c55e0d] text-[#22c55eaa]",
  danger: "border border-dashed border-[#dc262666] bg-[#dc26260d] text-[#dc2626aa]",
};

type ButtonProps = Omit<
  ButtonHTMLAttributes<HTMLButtonElement>,
  "onAnimationStart" | "onAnimationEnd" | "onDrag" | "onDragStart" | "onDragEnd"
> & {
  variant?: Variant;
  // React 19 hands `ref` to a function component as an ordinary prop, and it is
  // spread onto the underlying motion.button below. Declared explicitly because
  // the type does not include it otherwise -- ConfirmDialog needs it to put
  // focus on Cancel rather than on the destructive button.
  ref?: Ref<HTMLButtonElement>;
};

export function Button({ variant = "primary", className = "", disabled, ...props }: ButtonProps) {
  return (
    <motion.button
      whileHover={disabled ? undefined : { scale: 1.03 }}
      whileTap={disabled ? undefined : { scale: 0.97 }}
      transition={{ duration: 0.15 }}
      disabled={disabled}
      className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors disabled:cursor-not-allowed ${
        disabled ? disabledClasses[variant] : variantClasses[variant]
      } ${className}`}
      {...props}
    />
  );
}

/**
 * The small, colourless action: "Add art", "Remove", "Edit".
 *
 * These were bare muted text with an accent hover, which next to a filled
 * button reads as a caption rather than something you can press -- "Add art"
 * beside a vivid red Delete looked like a label for it. An outline gives them
 * a hit area and says "button" without spending a colour on it, which is the
 * whole point: they carry no status, so they should carry no status colour.
 */
export const ghostButtonClass =
  "inline-flex items-center gap-1 rounded-md border border-[var(--color-border)] " +
  // A raised neutral fill as well as the outline, and it has to be a fill you
  // can actually see: `--color-surface-2` sits about eight points a channel
  // above the card it lands on, which measured as applied and looked like
  // nothing changed. `--color-raised` is a real step off the surface, and is a
  // token so it can step *up* on dark and *down* on light -- a grey block on
  // white reads as disabled rather than as a control.
  // Neutral on purpose -- these carry no status, so they must not borrow a
  // status colour just to look pressable.
  "bg-[var(--color-raised)] px-2 py-1 text-xs text-[var(--color-text)] " +
  "transition-colors hover:border-[var(--color-accent)] " +
  "hover:bg-[var(--color-raised-hover)] hover:text-[var(--color-text)]";

export function ErrorText({ children }: PropsWithChildren) {
  if (!children) return null;
  return <p className="text-sm text-red-400">{children}</p>;
}

const fieldClass =
  "w-full rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]";

/**
 * Drops a default that the caller has overridden.
 *
 * Tailwind emits both `w-full` and a caller's `w-20`, and which one applies is
 * decided by their order in the generated stylesheet, not by the order they are
 * written here -- so appending simply lost. A "w-20" field silently filled its
 * row and collapsed whatever sat beside it, and a field given its own
 * horizontal padding kept the wider default and clipped its own value.
 *
 * `min-w-`/`max-w-` are left alone: those constrain a full-width field rather
 * than contradicting it.
 */
function fieldClassWith(extra?: string) {
  const own = extra ?? "";
  let base = fieldClass;
  if (/(^|\s)(w-(?!full)|size-)/.test(own)) base = base.replace("w-full ", "");
  if (/(^|\s)(px-|pl-|pr-|p-)/.test(own)) base = base.replace("px-3 ", "");
  return `${base} ${own}`;
}

/** Types whose browser picker only opens from the little icon at the edge. */
const PICKER_TYPES = new Set(["date", "time", "datetime-local", "month", "week"]);

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  const { onClick, ...rest } = props;

  // Clicking anywhere in a date or time field opens its picker, rather than
  // only the few pixels of calendar/clock icon at the right-hand edge --
  // clicking the middle of one and having nothing happen reads as broken.
  function handleClick(event: React.MouseEvent<HTMLInputElement>) {
    onClick?.(event);
    if (!PICKER_TYPES.has(props.type ?? "") || props.readOnly || props.disabled) return;
    try {
      // Not in every browser, and it throws where the field isn't ready for
      // it; either way the native icon still works, so failure is silent.
      event.currentTarget.showPicker?.();
    } catch {
      /* empty */
    }
  }

  return <input {...rest} onClick={handleClick} className={fieldClassWith(props.className)} />;
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={fieldClassWith(props.className)} />;
}

/** Flattens an <option>'s children to plain text, so labels built from several
 *  expressions ("Monthly - 1500 (30d)") still read correctly in the trigger. */
function textOf(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (isValidElement(node)) return textOf((node.props as { children?: ReactNode }).children);
  return "";
}

interface OptionItem {
  value: string;
  label: string;
  disabled: boolean;
}

function readOptions(children: ReactNode): OptionItem[] {
  return Children.toArray(children)
    .filter((child): child is ReactElement<Record<string, unknown>> =>
      isValidElement(child) && child.type === "option"
    )
    .map((child) => ({
      value: String(child.props.value ?? ""),
      label: textOf(child.props.children as ReactNode),
      disabled: Boolean(child.props.disabled),
    }));
}

const CHEVRON = (
  <svg viewBox="0 0 20 20" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth={2}>
    <path d="M6 8l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/**
 * Dropdown that takes the same `<option>` children and `e.target.value` change
 * handler as the native element it replaces, so call sites didn't have to move.
 *
 * A real (transparent) <select> stays underneath: it keeps the control inside
 * its form, so `required` still triggers the browser's own validation instead
 * of the page silently posting an empty value. The visible list renders through
 * a portal because several of these sit inside horizontally scrolling tables,
 * which would otherwise clip the panel.
 */
export function Select({
  value,
  onChange,
  className = "",
  disabled,
  required,
  children,
  ...rest
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange"> & {
  onChange?: (event: { target: { value: string } }) => void;
}) {
  const options = useMemo(() => readOptions(children), [children]);
  const current = String(value ?? "");
  const selected = options.find((o) => o.value === current);

  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const place = useCallback(() => {
    if (triggerRef.current) setRect(triggerRef.current.getBoundingClientRect());
  }, []);

  // Position can only be measured once the trigger has been laid out, so this
  // genuinely belongs in an effect; the highlighted row is set when opening.
  useLayoutEffect(() => {
    if (open) place();
  }, [open, place]);

  function openMenu() {
    setActive(Math.max(options.findIndex((o) => o.value === current), 0));
    setOpen(true);
  }

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!triggerRef.current?.contains(target) && !panelRef.current?.contains(target)) {
        setOpen(false);
      }
    };
    // Reposition rather than close, so scrolling with a list open isn't jarring.
    window.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, place]);

  function pick(option: OptionItem) {
    if (option.disabled) return;
    onChange?.({ target: { value: option.value } });
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (disabled) return;
    if (!open && (e.key === "Enter" || e.key === " " || e.key === "ArrowDown")) {
      e.preventDefault();
      openMenu();
      return;
    }
    if (!open) return;

    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, options.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (options[active]) pick(options[active]);
    }
  }

  // Flip above the trigger when there isn't room below.
  const panelMax = 260;
  const below = rect ? window.innerHeight - rect.bottom - 8 : 0;
  const dropUp = rect ? below < Math.min(panelMax, options.length * 38 + 8) && rect.top > below : false;

  return (
    <div className={`relative ${className}`}>
      <select
        {...rest}
        value={value}
        onChange={(e) => onChange?.({ target: { value: e.target.value } })}
        required={required}
        disabled={disabled}
        tabIndex={-1}
        aria-hidden
        className="pointer-events-none absolute inset-0 h-full w-full opacity-0"
      >
        {children}
      </select>

      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openMenu())}
        onKeyDown={onKeyDown}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={`flex w-full items-center justify-between gap-2 rounded-md border bg-[var(--color-surface-2)] px-3 py-2 text-left text-sm text-[var(--color-text)] outline-none transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          open ? "border-[var(--color-accent)]" : "border-[var(--color-border)]"
        }`}
      >
        <span className={`truncate ${selected ? "" : "text-[var(--color-text-muted)]"}`}>
          {selected?.label || options[0]?.label || ""}
        </span>
        <span
          className={`text-[var(--color-text-muted)] transition-transform duration-150 ${
            open ? "rotate-180" : ""
          }`}
        >
          {CHEVRON}
        </span>
      </button>

      {open &&
        rect &&
        createPortal(
          <div
            ref={panelRef}
            role="listbox"
            style={{
              position: "fixed",
              left: rect.left,
              width: rect.width,
              ...(dropUp
                ? { bottom: window.innerHeight - rect.top + 6 }
                : { top: rect.bottom + 6 }),
              maxHeight: panelMax,
            }}
            className="no-scrollbar z-50 overflow-y-auto rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] py-1 shadow-[0_12px_32px_-8px_rgba(0,0,0,0.7)]"
          >
            {options.map((option, i) => {
              const isSelected = option.value === current;
              return (
                <div
                  key={option.value + i}
                  role="option"
                  aria-selected={isSelected}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => pick(option)}
                  className={`cursor-pointer border-b border-[var(--color-border)]/60 px-3 py-2 text-sm last:border-none ${
                    option.disabled ? "cursor-not-allowed opacity-40" : ""
                  } ${
                    isSelected
                      ? "bg-[var(--color-accent)] font-semibold text-white"
                      : i === active
                        ? "bg-[var(--color-surface)] text-[var(--color-text)]"
                        : "text-[var(--color-text-muted)]"
                  }`}
                >
                  {option.label}
                </div>
              );
            })}
          </div>,
          document.body
        )}
    </div>
  );
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
