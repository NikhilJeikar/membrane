/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#212121",
          sidebar: "#171717",
          card: "#262626",
          elevated: "#2f2f2f",
          hover: "#383838",
          input: "#303030",
        },
        ink: {
          primary: "#ececec",
          secondary: "#b4b4b4",
          muted: "#8e8e8e",
        },
        accent: {
          DEFAULT: "#10a37f",
          hover: "#0d8c6d",
          muted: "#1a3d34",
        },
        line: {
          DEFAULT: "rgba(255,255,255,0.08)",
          strong: "rgba(255,255,255,0.16)",
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "Menlo", "monospace"],
      },
      boxShadow: {
        composer: "0 0 0 1px rgba(255,255,255,0.06), 0 8px 24px rgba(0,0,0,0.35)",
        overlay: "0 16px 48px rgba(0,0,0,0.5)",
      },
      keyframes: {
        pulseDot: {
          "0%, 80%, 100%": { opacity: "0.35", transform: "scale(0.85)" },
          "40%": { opacity: "1", transform: "scale(1)" },
        },
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.2s ease-in-out infinite",
        fadeIn: "fadeIn 0.15s ease-out",
      },
    },
  },
  plugins: [],
};
