-- Apply once, after 001_schema.sql and the chosen-dimension 002_embeddings.sql.
BEGIN;
SET LOCAL search_path = public;
ALTER TABLE knowledge_documents
    ADD COLUMN requested_revision_id uuid,
    ADD COLUMN ingestion_generation bigint NOT NULL DEFAULT 0 CHECK (ingestion_generation >= 0),
    ADD COLUMN requested_embedding_config_hash text,
    ADD CONSTRAINT knowledge_requested_target_check CHECK (
        (ingestion_generation = 0 AND requested_revision_id IS NULL AND requested_embedding_config_hash IS NULL)
        OR (ingestion_generation > 0 AND requested_revision_id IS NOT NULL AND requested_embedding_config_hash IS NOT NULL)),
    ADD CONSTRAINT knowledge_requested_revision_fk FOREIGN KEY (document_id, requested_revision_id)
        REFERENCES knowledge_document_revisions(document_id, id) ON DELETE RESTRICT;
CREATE INDEX knowledge_requested_revision_idx ON knowledge_documents(requested_revision_id);

CREATE TABLE embedding_jobs (
    id uuid PRIMARY KEY,
    document_id text NOT NULL REFERENCES knowledge_documents ON DELETE RESTRICT,
    revision_id uuid NOT NULL,
    generation bigint NOT NULL CHECK (generation > 0),
    model_id uuid NOT NULL REFERENCES embedding_models ON DELETE RESTRICT,
    chunker_version text NOT NULL,
    config_hash text NOT NULL,
    config jsonb NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','completed','failed','superseded')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    available_at timestamptz NOT NULL DEFAULT now(),
    claim_token uuid,
    lease_expires_at timestamptz,
    last_error_code text CHECK (length(last_error_code) <= 80),
    last_error text CHECK (length(last_error) <= 240),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    UNIQUE (document_id, generation),
    FOREIGN KEY (document_id, revision_id) REFERENCES knowledge_document_revisions(document_id,id) ON DELETE RESTRICT,
    CHECK ((status = 'processing' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR (status <> 'processing' AND claim_token IS NULL AND lease_expires_at IS NULL)),
    CHECK ((status IN ('completed','failed','superseded')) = (finished_at IS NOT NULL))
);
CREATE INDEX embedding_jobs_pending_idx ON embedding_jobs(available_at,created_at,id) WHERE status='pending';
CREATE INDEX embedding_jobs_lease_idx ON embedding_jobs(lease_expires_at) WHERE status='processing';
CREATE INDEX embedding_jobs_revision_idx ON embedding_jobs(revision_id);
CREATE INDEX embedding_jobs_model_idx ON embedding_jobs(model_id);

-- Admission locks the model row FOR SHARE before inserting its first job.
-- UPDATE's conflicting row lock closes the concurrent first-job race.
CREATE FUNCTION protect_embedding_model_identity() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.provider,NEW.model_name,NEW.model_revision,NEW.dimensions,NEW.distance_metric)
        IS DISTINCT FROM ROW(OLD.provider,OLD.model_name,OLD.model_revision,OLD.dimensions,OLD.distance_metric)
        AND EXISTS (SELECT 1 FROM embedding_jobs WHERE model_id=OLD.id) THEN
        RAISE EXCEPTION 'Model identity referenced by jobs is immutable' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER embedding_model_identity BEFORE UPDATE ON embedding_models
    FOR EACH ROW EXECUTE FUNCTION protect_embedding_model_identity();
COMMIT;
