/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./node_modules/@foundry/ui/src/**/*.{ts,tsx}", "./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Nyquest / SYNTHESIS palette
        bg: "#14161f",
        panel: "#1e2130",
        panel2: "#181b27",
        line: "#2a2d3a",
        cy: "#4fd1c5",
        vi: "#7c5cfc",
        ind: "#818cf8",
        ink: "#e8e9ef",
        dim: "#9aa0b0",
        ok: "#22c55e",
        warn: "#f4b860",
        bad: "#ef4444",
      },
      fontFamily: {
        mono: ["ui-monospace", "Cascadia Code", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
