import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "var(--canvas)",
        surface: "var(--surface)",
        ink: "var(--ink)",
        brand: "var(--brand)",
      },
      borderRadius: {
        card: "var(--radius-lg)",
      },
    },
  },
  plugins: [],
} satisfies Config;
