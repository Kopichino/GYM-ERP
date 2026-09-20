import { motion, useReducedMotion } from "framer-motion";
import type { PropsWithChildren } from "react";
import { EASE_SOFT } from "./siteMotion";

type Direction = "up" | "left" | "right" | "none";

/** Travel is deliberately short. A 20px settle at nine tenths of a second
 * reads as weight; a 60px slide at half a second reads as a slide. */
const OFFSETS: Record<Direction, { x: number; y: number }> = {
  up: { x: 0, y: 20 },
  left: { x: -20, y: 0 },
  right: { x: 20, y: 0 },
  none: { x: 0, y: 0 },
};

/** Scroll-triggered fade and settle, used for section entrances.
 *
 * Fires once, well before the element reaches the viewport edge, so content is
 * already resolving by the time the visitor's eye arrives at it. Under reduced
 * motion it renders the children in place with no wrapper animation at all. */
export default function Reveal({
  children,
  direction = "up",
  delay = 0,
  duration = 0.9,
  className = "",
  as = "div",
}: PropsWithChildren<{
  direction?: Direction;
  delay?: number;
  duration?: number;
  className?: string;
  as?: "div" | "li" | "span" | "figure";
}>) {
  const reduced = useReducedMotion();

  if (reduced) {
    const Plain = as;
    return <Plain className={className}>{children}</Plain>;
  }

  const Tag = motion[as];
  const { x, y } = OFFSETS[direction];

  return (
    <Tag
      initial={{ opacity: 0, x, y }}
      whileInView={{ opacity: 1, x: 0, y: 0 }}
      viewport={{ once: true, margin: "-12% 0px -12% 0px" }}
      transition={{ duration, delay, ease: EASE_SOFT }}
      className={className}
    >
      {children}
    </Tag>
  );
}
