# PostgreSQL Persistence

The optional adapter isolates driver imports, connections, migrations, and dialect
SQL. Applications pass a safe reference; the DSN is resolved only while connecting
and is never included in mapped errors. Migrations use an explicit version row and
transaction-scoped advisory lock. Newer unknown versions are rejected.

The normal test suite requires no PostgreSQL. A securely configured
`ASCOS_POSTGRES_TEST_URL` enables optional integration verification; its value must
never be logged.
