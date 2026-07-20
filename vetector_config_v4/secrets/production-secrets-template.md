# Production secrets template

Do not commit filled values to Git.

```txt
DATABASE_URL=postgresql://...
API_BASE_URL=https://...
BENV_CSV_URL=https://...
```

Recommended storage:

- Render environment variables for deployed services.
- GitHub Actions secrets/variables for scheduled imports and smoke tests.
- Local `.env` files only for development.
