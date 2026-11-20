Schema v1 is defined by the SQLAlchemy models and created at startup via Base.metadata.create_all. For this local small application no destructive migration is run. Back up named db-data before modifying schemas.

Domain revision (grid registration): the `observations` table now stores one press sheet per row with
`source_key`, alignment `angle` (0/90/180/270), `rows`, `cols`, and a `grids` JSON object holding the two
process grids `{'a': [[...]], 'b': [[...]]}` where `null` marks a missing cell. This replaces the former
scalar `values` JSON. Because columns are re-purposed rather than added, an existing v1 database must be
recreated (`docker compose down -v`) and re-seeded; no in-place data migration is provided.
