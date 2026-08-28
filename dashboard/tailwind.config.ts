import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // one deliberate accent (indigo), everything else neutral zinc
        brand: {
          DEFAULT: "#4f46e5",
          dark: "#4338ca",
        },
        ink: "#18181b", // zinc-900
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Inter",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(0 0 0 / 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
