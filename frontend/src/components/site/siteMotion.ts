/** The public site's two easing curves and its parallax spring.
 *
 * Kept apart from the app's own `lib/motion.ts`: the portal's motion is quick
 * and functional, the website's is slow and weighted, and the two should not
 * drift towards each other because they happened to share a file. */
export const EASE_SOFT = [0.22, 1, 0.36, 1] as const;
export const EASE_EXPO = [0.16, 1, 0.3, 1] as const;

/** Spring applied to scroll progress before it drives any parallax.
 *
 * Without it a parallax layer tracks the scroll wheel exactly, which is what
 * makes cheap parallax feel mechanical and notchy on a trackpad. Smoothing the
 * progress value first lets the layer lag and settle. */
export const PARALLAX_SPRING = {
  stiffness: 90,
  damping: 28,
  mass: 0.5,
  restDelta: 0.0005,
} as const;
