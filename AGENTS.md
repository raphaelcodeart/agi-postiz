This project is a multi-tenant social publishing platform.

Core rules:

1. Every campaign destination is an independent publication.
2. Never retry successful publications.
3. Never recreate an already submitted or published post without explicit administrator action.
4. PostgreSQL is the source of truth.
5. Redis and Celery are execution mechanisms only.
6. Every external request must be traceable to a Publication Attempt.
7. Use deterministic idempotency keys.
8. Never expose Buffer tokens to the frontend.
9. Encrypt OAuth tokens at rest.
10. Never log credentials or authorization headers.
11. Every database modification requires an Alembic migration.
12. All timestamps must be stored in UTC.
13. User-facing scheduled dates must preserve the selected timezone.
14. Do not invent undocumented Buffer API fields.
15. Production integration placeholders must be clearly marked.
16. Mock integrations must never activate in production.
17. Run tests and type checks after meaningful changes.
18. Prefer small, coherent changes.
19. Maintain backward compatibility unless a migration is explicitly planned.
20. Document architectural changes.
