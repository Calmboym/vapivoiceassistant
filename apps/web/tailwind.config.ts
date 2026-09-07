import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        midnight: "#0B1220",
        panel: "#121B2E",
        brass: "#C89B3C",
        "brass-soft": "#E8C874",
        mist: "#8B93A7",
        paper: "#EDEFF4",
        ok: "#4ADE80",
        warn: "#F87171",
      },
      fontFamily: {
        display: ["var(--font-display)"],
        mono: ["var(--font-mono)"],
      },
      letterSpacing: {
        widest2: "0.28em",
      },
    },
  },
  plugins: [],
};

export default config;
