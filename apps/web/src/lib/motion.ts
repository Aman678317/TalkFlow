/**
 * House motion values, modeled on Apple HIG springs (WWDC "Designing Fluid Interfaces").
 * Damping 1.0 (bounce 0) is the default; bounce is reserved for momentum-driven surfaces.
 * All components opt into prefers-reduced-motion via <MotionConfig reducedMotion="user"> in main.tsx.
 */
import type { Transition, Variants } from "motion/react";

/** Critically damped, quick — buttons, toggles, small state changes. */
export const springSnappy: Transition = { type: "spring", bounce: 0, duration: 0.3 };

/** Critically damped, graceful — page content, cards, panels. */
export const springSoft: Transition = { type: "spring", bounce: 0, duration: 0.42 };

/** Slight overshoot for momentum surfaces — sheets, modals, drawers. */
export const springSheet: Transition = { type: "spring", bounce: 0.18, duration: 0.38 };

/** Short opacity-only fade — used where transforms would be distracting. */
export const fadeFast: Transition = { duration: 0.15, ease: "easeOut" };

export const EASE_STANDARD = [0.16, 1, 0.3, 1] as const;

/** Page-level enter/exit for shell Outlets (paired with AnimatePresence mode="wait"). */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 10 },
  enter: { opacity: 1, y: 0, transition: springSoft },
  exit: { opacity: 0, y: -6, transition: { duration: 0.14, ease: "easeIn" } },
};

/** Scroll-triggered reveal (once). Transform is auto-disabled under reduced motion. */
export const revealVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: { opacity: 1, y: 0, transition: springSoft },
};

/** Container that staggers its children (items must use staggerItemVariants). */
export const staggerContainerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.055, delayChildren: 0.05 } },
};

export const staggerItemVariants: Variants = {
  hidden: { opacity: 0, y: 14 },
  visible: { opacity: 1, y: 0, transition: springSoft },
};

/** Tap feedback scale for pressable surfaces. */
export const PRESS_SCALE = 0.97;
export const TAP_TRANSITION: Transition = { type: "spring", bounce: 0, duration: 0.2 };
