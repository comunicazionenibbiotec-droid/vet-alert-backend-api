# GitHub repository variables and secrets

## Repository secrets

Create these under **Settings → Secrets and variables → Actions → Secrets**:

```txt
DATABASE_URL
```

## Repository variables

Create these under **Settings → Secrets and variables → Actions → Variables**:

```txt
API_BASE_URL=https://CHANGE_ME_VETECTOR_API_URL
BENV_CSV_URL=https://CHANGE_ME_BENV_EXPORT.csv
```

`BENV_CSV_URL` can remain empty until the BENV / IZS export is available.
