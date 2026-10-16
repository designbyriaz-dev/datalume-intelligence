import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "media",
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eef4ff",
          100: "#d9e6ff",
          300: "#93b4ff",
          500: "#3b6dfb",
          600: "#2651db",
          700: "#1c3fb0",
          900: "#111f52",
        },
      },
    },
  },
  plugins: [],
};

export default config;
