# Development conventions

- Keep geographic decisions in `backend/geopol/domain`, independent of HTTP and persistence.
- Never commit institutional datasets, credentials, generated exports, or local databases.
- Preserve source rows. A missing reference is different from a completed search without matches.
- Every result must retain method, provenance, spatial precision, evidence, and revision.
- Run backend tests and frontend type checks/build before committing relevant changes.
- Use Conventional Commits, with a scope when useful. Do not rewrite existing history.
- Use synthetic fixtures for tests and demos. No public geocoding or remote basemap by default.
