# RoutePilot contract schemas

These JSON Schema 2020-12 documents are generated from the strict Pydantic
models in `packages/python/routepilot_contracts`. Every object is closed with
`additionalProperties: false`, every public contract carries
`schema_version: 1`, and breaking changes require a new major-version file.

Regenerate from the repository root with:

```bash
PYTHONPATH=packages/python/routepilot_contracts/src \
  python -m routepilot_contracts.generate --output-root schemas
```

Committed schemas are checked byte-for-structure against the generator by the
contract test suite. Do not edit generated JSON by hand.
