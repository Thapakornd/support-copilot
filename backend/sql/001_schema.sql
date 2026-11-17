-- PostgreSQL 16. Apply once as the migration owner, before 002_embeddings.sql.
-- UUIDs come from the application. Historical foreign keys use RESTRICT.
BEGIN;
SET LOCAL search_path = public;

CREATE TABLE accounts (
    id uuid PRIMARY KEY,
    name text NOT NULL,
    plan_code text NOT NULL DEFAULT 'developer',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id uuid PRIMARY KEY,
    auth_issuer text NOT NULL,
    auth_subject text NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('customer', 'agent')),
    company text,
    phone text,
    timezone text NOT NULL DEFAULT 'UTC',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (auth_issuer, auth_subject)
);

CREATE TABLE account_memberships (
    account_id uuid NOT NULL REFERENCES accounts ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES users ON DELETE RESTRICT,
    team_role text NOT NULL,
    can_open_cases boolean NOT NULL DEFAULT true,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, user_id)
);
CREATE INDEX account_memberships_user_idx ON account_memberships (user_id, account_id);

CREATE TABLE notification_preferences (
    user_id uuid PRIMARY KEY REFERENCES users ON DELETE RESTRICT,
    replies boolean NOT NULL DEFAULT true,
    status_changes boolean NOT NULL DEFAULT true,
    weekly_digest boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE categories (
    id text PRIMARY KEY,
    label text NOT NULL,
    sort_order smallint NOT NULL
);

-- Preserve the existing JSONB staging importer and all imported rows.
CREATE TABLE IF NOT EXISTS knowledge_documents (
    document_id text PRIMARY KEY,
    data jsonb NOT NULL
);
ALTER TABLE knowledge_documents
    ADD COLUMN is_active boolean NOT NULL DEFAULT true,
    ADD COLUMN current_revision_id uuid,
    ADD COLUMN created_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();

CREATE TABLE knowledge_document_revisions (
    id uuid PRIMARY KEY,
    document_id text NOT NULL REFERENCES knowledge_documents ON DELETE RESTRICT,
    revision_hash text NOT NULL,
    content_hash text NOT NULL,
    title text NOT NULL,
    source_url text NOT NULL,
    source_type text NOT NULL,
    product text NOT NULL,
    deployment text NOT NULL,
    version_scope text NOT NULL,
    category_id text NOT NULL REFERENCES categories ON DELETE RESTRICT,
    topics text[] NOT NULL,
    content_markdown text NOT NULL,
    excerpt text NOT NULL,
    display_body jsonb,
    source_payload jsonb NOT NULL,
    fetched_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (document_id, revision_hash),
    UNIQUE (document_id, id)
);
ALTER TABLE knowledge_documents ADD CONSTRAINT knowledge_documents_current_revision_fk
    FOREIGN KEY (document_id, current_revision_id)
    REFERENCES knowledge_document_revisions (document_id, id) ON DELETE RESTRICT;
CREATE INDEX knowledge_documents_current_revision_idx ON knowledge_documents (current_revision_id);
CREATE INDEX knowledge_revisions_facets_idx
    ON knowledge_document_revisions (category_id, product, source_type);
CREATE INDEX knowledge_revisions_search_idx ON knowledge_document_revisions USING gin
    (to_tsvector('english', title || ' ' || excerpt || ' ' || content_markdown));

CREATE TABLE knowledge_chunk_sets (
    id uuid PRIMARY KEY,
    revision_id uuid NOT NULL REFERENCES knowledge_document_revisions ON DELETE RESTRICT,
    chunker_version text NOT NULL,
    config_hash text NOT NULL,
    state text NOT NULL CHECK (state IN ('preparing', 'ready', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (revision_id, chunker_version, config_hash),
    UNIQUE (revision_id, id)
);

-- The scraper owns knowledge_chunks(chunk_id, document_id, data). Keep it intact;
-- application chunks belong to immutable revision/configuration-specific sets.
CREATE TABLE knowledge_revision_chunks (
    chunk_set_id uuid NOT NULL REFERENCES knowledge_chunk_sets ON DELETE RESTRICT,
    chunk_id text NOT NULL,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    heading_path text[] NOT NULL,
    text text NOT NULL,
    char_count integer NOT NULL CHECK (char_count > 0),
    oversized boolean NOT NULL,
    PRIMARY KEY (chunk_set_id, chunk_id),
    UNIQUE (chunk_set_id, chunk_index)
);
CREATE INDEX knowledge_revision_chunks_search_idx ON knowledge_revision_chunks USING gin (to_tsvector('english', text));

CREATE TABLE embedding_models (
    id uuid PRIMARY KEY,
    provider text NOT NULL,
    model_name text NOT NULL,
    model_revision text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    distance_metric text NOT NULL,
    is_active boolean NOT NULL,
    UNIQUE (provider, model_name, model_revision, dimensions)
);

CREATE TABLE retrieval_publications (
    document_id text PRIMARY KEY REFERENCES knowledge_documents ON DELETE RESTRICT,
    chunk_set_id uuid NOT NULL REFERENCES knowledge_chunk_sets ON DELETE RESTRICT,
    model_id uuid NOT NULL REFERENCES embedding_models ON DELETE RESTRICT,
    published_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX retrieval_publications_chunk_set_idx ON retrieval_publications (chunk_set_id);
CREATE INDEX retrieval_publications_model_idx ON retrieval_publications (model_id);

CREATE TABLE ai_interactions (
    id uuid PRIMARY KEY,
    account_id uuid NOT NULL,
    user_id uuid NOT NULL,
    category_id text REFERENCES categories ON DELETE RESTRICT,
    question text NOT NULL,
    answer text,
    state text NOT NULL CHECK (state IN ('pending', 'completed', 'failed')),
    model_name text,
    prompt_version text,
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    FOREIGN KEY (account_id, user_id) REFERENCES account_memberships ON DELETE RESTRICT,
    UNIQUE (account_id, user_id, id),
    UNIQUE (id, user_id),
    CHECK (state <> 'completed' OR (answer IS NOT NULL AND completed_at IS NOT NULL)),
    CHECK (state <> 'failed' OR error_code IS NOT NULL)
);
CREATE INDEX ai_interactions_account_user_idx ON ai_interactions (account_id, user_id, created_at DESC, id);
CREATE INDEX ai_interactions_category_idx ON ai_interactions (category_id);

CREATE TABLE tickets (
    id uuid PRIMARY KEY,
    case_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    account_id uuid NOT NULL,
    reporter_id uuid NOT NULL,
    assignee_id uuid REFERENCES users ON DELETE RESTRICT,
    category_id text NOT NULL REFERENCES categories ON DELETE RESTRICT,
    title text NOT NULL CHECK (length(btrim(title)) > 0),
    description text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('draft', 'submitted', 'in_progress', 'waiting_for_customer', 'resolved')),
    severity smallint NOT NULL DEFAULT 2 CHECK (severity BETWEEN 1 AND 4),
    ai_interaction_id uuid,
    ai_answer_snapshot text,
    consent_at timestamptz NOT NULL,
    consent_version text NOT NULL,
    version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (account_id, reporter_id) REFERENCES account_memberships ON DELETE RESTRICT,
    FOREIGN KEY (account_id, reporter_id, ai_interaction_id)
        REFERENCES ai_interactions (account_id, user_id, id) ON DELETE RESTRICT,
    CHECK ((status = 'resolved') = (resolved_at IS NOT NULL))
);
CREATE INDEX tickets_account_updated_idx ON tickets (account_id, updated_at DESC, id);
CREATE INDEX tickets_updated_idx ON tickets (updated_at DESC, id);
CREATE INDEX tickets_unassigned_queue_idx ON tickets (severity DESC, created_at, id)
    WHERE status IN ('submitted', 'in_progress', 'waiting_for_customer') AND assignee_id IS NULL;
CREATE INDEX tickets_assignee_queue_idx ON tickets (assignee_id, severity DESC, created_at, id)
    WHERE status IN ('submitted', 'in_progress', 'waiting_for_customer');
CREATE INDEX tickets_assignee_idx ON tickets (assignee_id);
CREATE INDEX tickets_reporter_idx ON tickets (reporter_id);
CREATE INDEX tickets_category_idx ON tickets (category_id);
CREATE INDEX tickets_ai_interaction_idx ON tickets (ai_interaction_id);
CREATE INDEX tickets_search_idx ON tickets USING gin (to_tsvector('english', title || ' ' || description));

CREATE TABLE ticket_entries (
    id uuid PRIMARY KEY,
    entry_number bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    ticket_id uuid NOT NULL REFERENCES tickets ON DELETE RESTRICT,
    actor_id uuid REFERENCES users ON DELETE RESTRICT,
    actor_name_snapshot text NOT NULL,
    actor_role text NOT NULL CHECK (actor_role IN ('customer', 'agent', 'system')),
    kind text NOT NULL CHECK (kind IN ('reply', 'event')),
    body text NOT NULL,
    event_type text,
    event_data jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (actor_id IS NOT NULL OR (kind = 'event' AND actor_role = 'system'))
);
CREATE INDEX ticket_entries_timeline_idx ON ticket_entries (ticket_id, entry_number);
CREATE INDEX ticket_entries_actor_idx ON ticket_entries (actor_id);

CREATE TABLE ticket_sources (
    ticket_id uuid NOT NULL REFERENCES tickets ON DELETE RESTRICT,
    position integer NOT NULL CHECK (position > 0),
    document_id text REFERENCES knowledge_documents ON DELETE RESTRICT,
    revision_id uuid,
    title_snapshot text NOT NULL,
    url_snapshot text,
    PRIMARY KEY (ticket_id, position),
    FOREIGN KEY (document_id, revision_id)
        REFERENCES knowledge_document_revisions (document_id, id) ON DELETE RESTRICT,
    CHECK (revision_id IS NULL OR document_id IS NOT NULL)
);
CREATE INDEX ticket_sources_revision_idx ON ticket_sources (document_id, revision_id);

CREATE TABLE ai_citations (
    interaction_id uuid NOT NULL REFERENCES ai_interactions ON DELETE RESTRICT,
    position integer NOT NULL CHECK (position > 0),
    revision_id uuid NOT NULL REFERENCES knowledge_document_revisions ON DELETE RESTRICT,
    chunk_set_id uuid NOT NULL,
    chunk_id text NOT NULL,
    title_snapshot text NOT NULL,
    url_snapshot text NOT NULL,
    excerpt_snapshot text NOT NULL,
    score double precision,
    PRIMARY KEY (interaction_id, position),
    FOREIGN KEY (revision_id, chunk_set_id)
        REFERENCES knowledge_chunk_sets (revision_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (chunk_set_id, chunk_id) REFERENCES knowledge_revision_chunks ON DELETE RESTRICT
);
CREATE INDEX ai_citations_revision_set_idx ON ai_citations (revision_id, chunk_set_id);
CREATE INDEX ai_citations_chunk_idx ON ai_citations (chunk_set_id, chunk_id);

CREATE TABLE answer_feedback (
    interaction_id uuid NOT NULL,
    user_id uuid NOT NULL REFERENCES users ON DELETE RESTRICT,
    vote smallint NOT NULL CHECK (vote IN (-1, 1)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (interaction_id, user_id),
    FOREIGN KEY (interaction_id, user_id) REFERENCES ai_interactions (id, user_id) ON DELETE RESTRICT
);
CREATE INDEX answer_feedback_user_idx ON answer_feedback (user_id);

CREATE TABLE article_feedback (
    document_id text NOT NULL REFERENCES knowledge_documents ON DELETE RESTRICT,
    user_id uuid NOT NULL REFERENCES users ON DELETE RESTRICT,
    vote smallint NOT NULL CHECK (vote IN (-1, 1)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, user_id)
);
CREATE INDEX article_feedback_user_idx ON article_feedback (user_id);

-- updated_at/version changes are explicit service responsibilities. In particular,
-- ticket updates, replies and events must commit together under a ticket lock/CAS.
COMMIT;
