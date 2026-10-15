/**
 * House motion values.
 *
 * Motion is reserved for hierarchy and feedback: a page enters with a small
 * lift, a surface follows the user's gesture, and opacity carries state
 * changes that do not need spatial movement. The app root opts into Motion's
 * user reduced-motion policy; Motion.tsx also guards its primitives so they
 * remain safe when rendered outside that root.
 */
import type { Transition, Variants } from "motion/react";

export const EASE_EMPHASIZED = [0.2, 0, 0, 1] as const;
export const EASE_STANDARD = [0.16, 1, 0.3, 1] as const;

/** Quick and quiet — buttons, toggles, and small state changes. */
export const springSnappy: Transition = {
  type: "spring",
  stiffness: 520,
  damping: 42,
  mass: 0.7,
};

/** Settled and legible — routed content, cards, and panels. */
export const springSoft: Transition = {
  type: "spring",
  stiffness: 380,
  damping: 34,
  mass: 0.8,
};

/** A restrained follow-through for sheets and dialogs. */
export const springSheet: Transition = {
  type: "spring",
  stiffness: 420,
  damping: 32,
  mass: 0.75,
  bounce: 0.08,
};

/** Short opacity-only fade — used where transforms would be distracting. */
export const fadeFast: Transition = { duration: 0.16, ease: "easeOut" };

/** Page-level enter/exit for shell Outlets (paired with AnimatePresence mode="wait"). */
export const pageVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  enter: { opacity: 1, y: 0, transition: springSoft },
  exit: { opacity: 0, y: -4, transition: { duration: 0.14, ease: "easeIn" } },
};

/** Scroll-triggered reveal (once). Keep the lift small so content remains primary. */
export const revealVariants: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: springSoft },
};

/** Container that staggers its children without creating a cascade. */
export const staggerContainerVariants: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.045, delayChildren: 0.03 } },
};

export const staggerItemVariants: Variants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: springSoft },
};

/** Tap feedback scale for pressable surfaces. */
export const PRESS_SCALE = 0.98;
export const TAP_TRANSITION: Transition = {
  type: "spring",
  stiffness: 600,
  damping: 45,
  mass: 0.55,
};
