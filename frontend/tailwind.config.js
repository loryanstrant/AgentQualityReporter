/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        slate: "var(--slate)",
        mist: "var(--mist)",
        surface: "var(--surface)",
        hairline: "var(--hairline)",
        track: "var(--track)",
        line: "var(--line)",
        strong: "var(--strong)",
        orange: "#ff5800",
        magenta: "#ce0569",
        pass: "#2A9D8F",
        fail: "#E63946",
        skip: "#8D99AE",
        manual: "#6C63FF",
        "sev-blocker": "#E63946",
        "sev-major": "#F4A261",
        "sev-minor": "#E9C46A",
        "sev-info": "#8AB0AB",
      },
      fontFamily: {
        sans: ['"Segoe UI"', '"Open Sans"', "Roboto", "Arial", "sans-serif"],
        mono: ["Consolas", '"SF Mono"', "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 2px 6px rgba(15,20,26,.06)",
        lg: "0 10px 30px rgba(15,20,26,.14)",
      },
    },
  },
  plugins: [],
};
