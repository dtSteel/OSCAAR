# OSCAAR Frontend

React application for the OSCAAR cancer research intelligence platform.

## Quick Start

```bash
# Install dependencies
npm install

# Start development server (proxies API to localhost:8000)
npm run dev

# Build for production
npm run build
```

## Development

The Vite dev server runs on http://localhost:3000 and proxies all `/api/*` requests to the FastAPI backend at http://localhost:8000.

Make sure the backend is running before starting the frontend:

```bash
# In the backend directory
docker compose up -d

# Then in this directory
npm run dev
```

## Production deployment

After `npm run build`, the `dist/` folder contains the static site. Serve it via Nginx:

```nginx
location / {
    root /home/oscaar/oscaar-frontend/dist;
    try_files $uri $uri/ /index.html;
}
```

## Structure

```
src/
├── api/client.js          — Axios instance + all API calls
├── context/AuthContext.jsx — JWT auth state
├── i18n/translations.js   — 5-language UI strings
├── styles/theme.css       — Global CSS variables and utilities
├── components/
│   ├── Logo.jsx           — OSCAAR SVG logo
│   └── Layout.jsx         — Topbar navigation
├── pages/
│   ├── Login.jsx          — Sign in / register / reset
│   ├── Search.jsx         — RAG query interface
│   ├── Documents.jsx      — Upload and manage documents
│   ├── Admin.jsx          — User management and reports
│   ├── EmailPreview.jsx   — Welcome email preview
│   └── Profile.jsx        — Password and language settings
└── App.jsx                — Router and protected routes
```

## Languages supported

English · Français · Deutsch · Español · 日本語
