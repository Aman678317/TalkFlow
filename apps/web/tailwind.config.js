/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // GlobalTalk AI identity: deep ink navy + signal teal + warm amber alerts
        ink: {
          50: "#f4f6fb", 100: "#e7ebf5", 200: "#c7d0e6", 300: "#9dabd0",
          400: "#6f82b4", 500: "#4f639b", 600: "#3d4d80", 700: "#323e67",
          800: "#242c49", 900: "#171d33", 950: "#0d1122",
        },
        signal: {
          50: "#effbf7", 100: "#d7f5ea", 200: "#b0ead6", 300: "#7cd9bd",
          400: "#48c19f", 500: "#23a685", 600: "#17866c", 700: "#146b58",
          800: "#135546", 900: "#11473c",
        },
        amber: {
          450: "#f5a623",
        },
      },
      fontFamily: {
        sans: ['"Inter"', '"Segoe UI"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(13,17,34,.05), 0 4px 16px rgba(13,17,34,.06)",
        pop: "0 8px 32px rgba(13,17,34,.16)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { transform: "scale(.9)", opacity: ".7" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
      },
      animation: { "pulse-ring": "pulse-ring 1.4s ease-out infinite" },
    },
  },
  plugins: [],
};
