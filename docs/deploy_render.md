# Deploy on Render

## 1. Create PostgreSQL/PostGIS database

Use a PostgreSQL database with PostGIS enabled. Run:

```bash
psql "$DATABASE_URL" -f db/schema.sql
psql "$DATABASE_URL" -f db/seed_data_sources.sql
psql "$DATABASE_URL" -f db/views_and_helpers.sql
```

## 2. Create Web Service

- Runtime: Node
- Build command: `npm install`
- Start command: `npm start`
- Environment variables:
  - `DATABASE_URL`
  - `CORS_ORIGIN=https://vet.ector.nibbiotec.com`
  - `NODE_ENV=production`

## 3. Front-end configuration

Set `window.API_BASE_URL_DEFAULT` in `/js/config.js` to the deployed API URL.

Example:

```js
window.API_BASE_URL_DEFAULT = 'https://your-vetector-api.onrender.com';
```
