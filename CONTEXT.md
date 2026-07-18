# SchemaFlight context

SchemaFlight is a metadata-grounded migration compiler for the DataHub Agent Hackathon.

Domain language:

- **Change request**: a proposed schema mutation against one DataHub dataset.
- **Asset context**: schema, ownership, governance, query, and multi-hop lineage evidence read from DataHub.
- **Blast radius**: downstream assets and queries that depend on the changed field.
- **Migration bundle**: deterministic SQL, tests, query patches, rollout/rollback guidance, and a manifest.
- **Decision document**: the human-readable migration record that can be written back to DataHub.
- **Catalog adapter**: a concrete reader/writer at the metadata seam. The repository includes a snapshot adapter and a live adapter backed by the official DataHub Agent Context Kit.

The compiler is a deep module. Its public interface accepts one change request plus one catalog adapter and returns one migration bundle. Network transport, traversal, risk rules, templates, and file layout remain implementation details.
