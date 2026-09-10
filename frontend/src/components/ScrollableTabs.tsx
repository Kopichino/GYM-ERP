import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Horizontal tab strip with an arrow button on each side instead of a visible
 * scrollbar. Clicking a tab that sits near either edge re-centres it, which is
 * what reveals the tabs beyond it -- otherwise the tab you just clicked stays
 * jammed against the edge with its neighbours still hidden.
 */
export default function ScrollableTabs({ children }: { children: React.ReactNode }) {
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(true);

  const syncArrows = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    // 1px of slack: fractional scroll widths never land exactly on the bound.
    setAtStart(el.scrollLeft <= 1);
    setAtEnd(el.scrollLeft >= el.scrollWidth - el.clientWidth - 1);
  }, []);

  useEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    syncArrows();
    const observer = new ResizeObserver(syncArrows);
    observer.observe(el);
    return () => observer.disconnect();
  }, [syncArrows, children]);

  function scrollByPage(direction: 1 | -1) {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollBy({ left: direction * el.clientWidth * 0.7, behavior: "smooth" });
  }

  /** Centre a tab that was clicked while sitting at (or past) either edge. */
  function handleTabClick(event: React.MouseEvent<HTMLDivElement>) {
    const el = scrollerRef.current;
    const tab = (event.target as HTMLElement).closest("a,button");
    if (!el || !tab || !el.contains(tab)) return;

    const strip = el.getBoundingClientRect();
    const box = tab.getBoundingClientRect();
    const edge = Math.min(96, strip.width * 0.25);
    const nearLeft = box.left - strip.left < edge;
    const nearRight = strip.right - box.right < edge;
    if (!nearLeft && !nearRight) return;

    const offset = box.left - strip.left - (strip.width - box.width) / 2;
    el.scrollBy({ left: offset, behavior: "smooth" });
  }

  const arrowClass =
    "shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1.5 text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-accent)] hover:text-[var(--color-text)] disabled:cursor-not-allowed disabled:opacity-30";

  return (
    <div className="flex min-w-0 flex-1 items-center gap-1">
      <button
        type="button"
        onClick={() => scrollByPage(-1)}
        disabled={atStart}
        aria-label="Scroll tabs left"
        className={arrowClass}
      >
        &#8249;
      </button>
      <div
        ref={scrollerRef}
        onScroll={syncArrows}
        onClick={handleTabClick}
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        {children}
      </div>
      <button
        type="button"
        onClick={() => scrollByPage(1)}
        disabled={atEnd}
        aria-label="Scroll tabs right"
        className={arrowClass}
      >
        &#8250;
      </button>
    </div>
  );
}
