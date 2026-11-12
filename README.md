# ACbridge

A full-stack demo app: **Express** REST API + **React (Vite)** client. No database or
external services needed - data is stored in a JSON file.

## Structure

```
ACbridge/
├── package.json        # npm workspaces + root scripts
├── server/             # Express API (port 4000)
│   ├── src/            #   app.js, index.js, store.js, routes/items.js
│   └── test/           #   API tests (node:test)
└── client/             # React + Vite UI (port 5173)
    └── src/            #   App.jsx, api.js, components/, styles.css
```

## Requirements

Node.js 18 or newer.

## Run it

```bash
git clone https://github.com/override0237/ACbridge.git
cd ACbridge
git checkout feature/initial-fullstack-demo   # until merged to main
npm install
npm run dev
```

Open http://localhost:5173 (the Vite dev server proxies `/api` to the API on port 4000).

## Other commands

| Command         | What it does                                              |
|-----------------|-----------------------------------------------------------|
| `npm test`      | Runs the API tests                                        |
| `npm run build` | Builds the client into `client/dist`                      |
| `npm start`     | Builds, then serves UI + API together at http://localhost:4000 |

## API

| Method | Path             | Body              |
|--------|------------------|-------------------|
| GET    | `/api/health`    |                   |
| GET    | `/api/items`     |                   |
| POST   | `/api/items`     | `{ "title": "" }` |
| PATCH  | `/api/items/:id` | `{ "done": true }`|
| DELETE | `/api/items/:id` |                   |
