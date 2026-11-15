# Ticket desk (frontend)

React + Vite + Tailwind. Talks to the FastAPI backend through `src/lib/api.js`.

```
npm install
npm run dev        # http://localhost:5173  (backend must run on http://127.0.0.1:8000)
npm run build      # production build in dist/
npm run lint
```

Set `VITE_API_URL` in `frontend/.env.local` (or in Vercel) to point at a different backend.
The backend must allow this origin in `CORS_ORIGINS`.

Layout: `App.jsx` (shell, status, tabs) · `components/TicketForm`, `Result`, `RouteTrack`, `Feedback`, `History` ·
`lib/words.js` (every plain-language label and the demo tickets) · `lib/stations.js` (turns the audit trace into the six stations).
Fonts are bundled with `@fontsource` so the app needs no external font server.
