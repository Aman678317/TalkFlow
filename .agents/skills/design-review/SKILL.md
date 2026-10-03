---
name: design-review
description: "UI/UX design review. Assesses visual hierarchy, typography, colors, animations, responsive layouts, accessibility (WCAG), empty/loading/error states, and micro-interactions."
---

# UI/UX Design Review Mode

Review frontend screens, components, user flows, and interactive elements to ensure high-craft aesthetics, accessibility, and fluid user feedback.

## Audit Checklist
1. **Visual Hierarchy & Typography**: Clear heading hierarchy, harmonious scale, optical alignment, no awkward line wraps.
2. **Color System & Contrast**: WCAG AA/AAA compliance, consistent semantic colors (success, error, warning, brand), dark/light mode balance.
3. **Interactive States**: Default, hover, active, focus-visible (accessibility ring), loading (skeleton or spinner), and disabled states on every interactive element.
4. **Resilience States**: Empty states (friendly copy + primary CTA), error states (actionable guidance + retry), network drop banners.
5. **Fluid Motion & Micro-interactions**: Smooth transitions (150-250ms), physical ease curves, spring-based dialogs/drawers, no layout shifts (CLS).
6. **Mobile & Viewport Responsiveness**: Touch targets (>=44x44px), thumb-zone ergonomics, no horizontal overflow, responsive breakpoints.
