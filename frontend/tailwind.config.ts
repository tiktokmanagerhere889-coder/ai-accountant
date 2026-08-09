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
        // All values below match Dashboard redesign spec §3 exactly.
        accent: {
          light: "#1D9E75", // --accent brand teal, identical in both modes
          dark: "#1D9E75",
        },
        background: {
          light: "#F7F8FA", // --bg-page light
          dark: "#0B0F14", // --bg-page dark (not pure black)
        },
        surface: {
          light: "#FFFFFF", // --bg-card light (1px #E5E7EB border via gray-200)
          dark: "#131A22", // --bg-card dark
        },
        danger: {
          light: "#C6362F", // --danger light (deeper red for AA on white)
          dark: "#E24B4A", // --danger dark
        },
        warning: {
          light: "#B57516", // --warning light (deeper amber for AA on white)
          dark: "#EF9F27", // --warning dark
        },
        success: {
          light: "#4C7A1B", // --success light (deeper green for AA on white)
          dark: "#639922", // --success dark — kept distinct from accent teal
        },
      },
    },
  },
  plugins: [],
};
export default config;
