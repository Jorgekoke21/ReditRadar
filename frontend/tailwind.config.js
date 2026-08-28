/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#062F25",
          hover: "#0A4638",
          active: "#04231C",
        },
        accent: "#A3FF12",
        surface: "#F1F8F5",
      },
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "12px",
      },
      boxShadow: {
        subtle: "0 1px 2px rgba(6, 47, 37, 0.06), 0 1px 1px rgba(6, 47, 37, 0.04)",
      },
    },
  },
  plugins: [],
};
