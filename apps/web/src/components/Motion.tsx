/**
 * Shared motion primitives. All honor prefers-reduced-motion through
 * <MotionConfig reducedMotion="user"> at the app root.
 */
import { motion, useInView, type HTMLMotionProps } from "motion/react";
import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  pageVariants,
  revealVariants,
  staggerContainerVariants,
  staggerItemVariants,
  PRESS_SCALE,
  TAP_TRANSITION,
} from "@/lib/motion";

/** Wraps a routed page for enter/exit transitions inside AnimatePresence. */
export function PageTransition({ className, children, ...rest }: HTMLMotionProps<"div">) {
  return (
    <motion.div
      variants={pageVariants}
      initial="initial"
      animate="enter"
      exit="exit"
      className={className}
      {...rest}
    >
      {children}
    </motion.div>
  );
}

/** Fades + lifts content into view once, when it first enters the viewport. */
export function Reveal({
  children,
  className,
  delay = 0,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  delay?: number;
  as?: "div" | "section" | "li" | "span";
}) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px 0px" });
  const Comp = motion[as] as typeof motion.div;
  return (
    <Comp
      ref={ref as never}
      variants={revealVariants}
      initial="hidden"
      animate={inView ? "visible" : "hidden"}
      transition={delay ? { delay } : undefined}
      className={className}
    >
      {children}
    </Comp>
  );
}

/** Stagger container — pair children with <StaggerItem>. Reveals on first in-view. */
export function Stagger({
  children,
  className,
  once = true,
}: {
  children: ReactNode;
  className?: string;
  once?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once, margin: "-32px 0px" });
  return (
    <motion.div
      ref={ref}
      variants={staggerContainerVariants}
      initial="hidden"
      animate={inView ? "visible" : "hidden"}
      className={className}
    >
      {children}
    </motion.div>
  );
}

export function StaggerItem({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <motion.div variants={staggerItemVariants} className={className}>
      {children}
    </motion.div>
  );
}

/** Adds subtle press feedback (scale on pointer-down) to any surface. */
export function Pressable({
  children,
  className,
  scale = PRESS_SCALE,
  ...rest
}: HTMLMotionProps<"div"> & { scale?: number }) {
  return (
    <motion.div
      whileTap={{ scale }}
      transition={TAP_TRANSITION}
      className={cn("select-none", className)}
      {...rest}
    >
      {children}
    </motion.div>
  );
}
