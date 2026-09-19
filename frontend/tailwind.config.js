/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#152019",
        pine: "#1f4d3a",
        sage: "#dce8de",
        paper: "#f7f6f0",
        clay: "#d8784f",
      },
      boxShadow: {
        card: "0 10px 34px rgba(23, 33, 25, 0.08)",
      },
    },
  },
  plugins: [],
};
