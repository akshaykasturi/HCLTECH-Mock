/** Design tokens live here so every component uses the same palette and type. */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#ECEEE8",      // page background: cool sage-grey
        sheet: "#F7F8F4",      // raised surfaces
        ink: "#17212B",        // main text
        steel: "#5A6875",      // secondary text
        rule: "#CDD2C8",       // dividers
        route: "#2C5BA6",      // primary action + the route track
        go: "#2D7A57",         // RECOMMEND
        hold: "#B4741A",       // CLARIFY
        stop: "#BE3A2E",       // ESCALATE
      },
      fontFamily: {
        sans: ['"Archivo Variable"', "system-ui", "sans-serif"],
        serif: ['"Source Serif 4 Variable"', "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
