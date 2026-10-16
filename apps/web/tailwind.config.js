/** @type {import('tailwindcss').Config} */

const ink = {
  50: "#F5F7F9",
  100: "#E9EDF2",
  200: "#D5DDE6",
  300: "#B8C3CF",
  400: "#91A0AF",
  500: "#6F7D8D",
  600: "#526172",
  700: "#39495B",
  800: "#233548",
  900: "#14263A",
  950: "#0B1728",
};

// The warm accent stays dark enough for white labels at every interactive step.
const accent = {
  50: "#FFF6EA",
  100: "#FFE9CC",
  200: "#FFD19A",
  300: "#FFB765",
  400: "#E98642",
  500: "#C45A2C",
  600: "#B64A23",
  700: "#963B1D",
  800: "#71301D",
  900: "#52251A",
};

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic palette used by the new shell and primitives.
        surface: {
          canvas: "#F4F6F8",
          panel: "#FFFFFF",
          raised: "#FFFFFF",
          subtle: "#E9EDF2",
          inverse: "#0B1728",
        },
        border: {
          DEFAULT: "#D5DDE6",
          strong: "#B8C3CF",
          inverse: "rgba(255,255,255,.14)",
        },
        accent,
        focus: "#F0A35B",

        // Existing page vocabulary is kept as a semantic alias, so page files
        // do not need to change as the foundation evolves.
        dl: {
          navy: "#0B1728",
          blue: accent[600],
          "blue-hover": accent[700],
          "blue-light": accent[50],
          "blue-mid": accent[200],
          bg: "#FFFFFF",
          "bg-alt": "#F4F6F8",
          border: ink[200],
          "border-mid": ink[300],
          muted: ink[500],
          faint: ink[400],
          pill: "#FCEBD8",
          "pill-active": accent[600],
        },
        ink,
        signal: accent,
        iris: accent,
        lagoon: accent,
        slate: ink,
        amber: { 450: "#E98642" },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "-apple-system", "sans-serif"],
        display: ["Space Grotesk", "Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(11,23,40,.04), 0 8px 24px rgba(11,23,40,.06)",
        pop: "0 18px 50px rgba(11,23,40,.18), 0 2px 8px rgba(11,23,40,.08)",
        panel: "0 0 0 1px rgba(11,23,40,.04)",
        xs: "0 1px 2px rgba(11,23,40,.06)",
        lift: "0 1px 2px rgba(11,23,40,.05), 0 14px 30px rgba(11,23,40,.12)",
        "lift-sm": "0 1px 2px rgba(11,23,40,.05), 0 6px 16px rgba(11,23,40,.08)",
        accent: "0 8px 20px rgba(182,74,35,.22)",
      },
      letterSpacing: {
        display: "-0.035em",
        title: "-0.022em",
      },
      borderRadius: {
        xl2: "14px",
        "2.5xl": "20px",
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.16, 1, 0.3, 1)",
        emphasized: "cubic-bezier(0.2, 0, 0, 1)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(.9)", opacity: ".7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(5px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-down": {
          from: { opacity: "0", transform: "translateY(-7px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(10px) scale(0.985)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.55" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.4s ease-out infinite",
        "fade-in": "fade-in 0.2s cubic-bezier(0.16, 1, 0.3, 1) both",
        "slide-down": "slide-down 0.2s cubic-bezier(0.16, 1, 0.3, 1) both",
        "slide-up": "slide-up 0.3s cubic-bezier(0.16, 1, 0.3, 1) both",
        "pulse-soft": "pulse-soft 1.8s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
