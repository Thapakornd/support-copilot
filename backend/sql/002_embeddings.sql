-- psql script: supply -v embedding_dimensions=<chosen model dimension>.
-- Do not run until a fixed embedding model/dimension has been selected.
\set ON_ERROR_STOP on
\if :{?embedding_dimensions}
\else
    \echo 'Required: -v embedding_dimensions=<chosen model dimension>'
    \quit 1
\endif
BEGIN;
SET LOCAL search_path = public;
CREATE EXTENSION IF NOT EXISTS vector;

-- Quoted input is validated as an integer before becoming a vector type modifier.
SELECT format($ddl$
    CREATE TABLE chunk_embeddings (
        chunk_set_id uuid NOT NULL,
        chunk_id text NOT NULL,
        model_id uuid NOT NULL REFERENCES embedding_models ON DELETE RESTRICT,
        embedding vector(%s) NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        PRIMARY KEY (chunk_set_id, chunk_id, model_id),
        FOREIGN KEY (chunk_set_id, chunk_id) REFERENCES knowledge_revision_chunks ON DELETE RESTRICT
    )
$ddl$, :'embedding_dimensions'::integer) \gexec
CREATE INDEX chunk_embeddings_model_idx ON chunk_embeddings (model_id);

-- The ingestion service must check the model's dimensions against this table,
-- reject zero vectors when using cosine, and never mix models in a query.
-- Start with exact search. Add a model-specific ANN index only after measuring.
COMMIT;
