import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        accent: {
          light: "#0d9488", // Deep Teal
          dark: "#0d9488",
        },
        background: {
          light: "#f9f8f6", // warm ivory
          dark: "#0d0f11", // dark charcoal
        },
        surface: {
          light: "#ffffff",
          dark: "#16191d",
        },
      },
    },
  },
  plugins: [],
};
export default config;
