import type { Variants } from "framer-motion";

/** Shared fade+slide-up entrance, used for cards/list items across pages. */
export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0 },
};

/** Wrap a list with this on the parent and `fadeUp` on each child to get a
 * staggered reveal instead of everything popping in at once. */
export function staggerContainer(stagger = 0.06): Variants {
  return {
    hidden: {},
    visible: { transition: { staggerChildren: stagger } },
  };
}

/** Route-content transition -- fade + small vertical shift on mount/unmount. */
export const pageTransition: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};
