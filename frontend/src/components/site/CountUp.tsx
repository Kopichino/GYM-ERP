import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

/** Counts from zero to `to` the first time it scrolls into view.
 *
 * The figure is the content, so reduced-motion visitors get the final value
 * immediately rather than having it withheld behind an animation. */
export default function CountUp({
  to,
  suffix = "",
  duration = 1500,
}: {
  to: number;
  suffix?: string;
  duration?: number;
}) {
  const reduced = useReducedMotion();
  const [value, setValue] = useState(reduced ? to : 0);
  const started = useRef(false);
  const raf = useRef(0);

  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  if (reduced) {
    return (
      <span>
        {to.toLocaleString()}
        {suffix}
      </span>
    );
  }

  return (
    <motion.span
      onViewportEnter={() => {
        if (started.current) return;
        started.current = true;
        const start = performance.now();
        const tick = (now: number) => {
          const t = Math.min((now - start) / duration, 1);
          setValue(Math.round(to * (1 - Math.pow(1 - t, 4))));
          if (t < 1) raf.current = requestAnimationFrame(tick);
        };
        raf.current = requestAnimationFrame(tick);
      }}
      viewport={{ once: true, margin: "-70px" }}
    >
      {value.toLocaleString()}
      {suffix}
    </motion.span>
  );
}
