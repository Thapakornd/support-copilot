# Connect published knowledge to chat

Each Ask submission sends one question and an optional product category. The embedding model turns that question into a search vector. PostgreSQL finds relevant published passages, and the chat model uses those passages to compose a cited answer. Publishing a document once makes it available to subsequent questions. A chat request only needs to encode the question.

## Workflow

```mermaid
flowchart TD
    subgraph P["Already implemented · when knowledge changes"]
      W["Embedding worker writes revision chunks and vectors"] --> PUB["Commit ready chunk set, model ID and current revision together"]
    end
    subgraph Q["Chat · once per Ask submission"]
      U["Ask page sends question and optional category"] --> API["POST /chat validates input"]
      API --> ENC["Encode question with the publication model and query prompt"]
      ENC --> DB["Search eligible published chunks by cosine distance"]
      DB --> G{"Enough relevant evidence?"}
      G -->|No| N["Return insufficient_evidence and a clarifying question"]
      G -->|Yes| L["Send question and numbered passages to chat model"]
      L --> V{"Answer cites supplied passages?"}
      V -->|Yes| A["Resolve citation IDs to published titles and URLs"]
      V -->|Unsupported answer| N
      A --> UI["Ask page shows answer and references"]
      N --> UI
      DB -. unavailable .-> E["Show service error with retry"]
      L -. unavailable .-> E
    end
    PUB --> DB
```

For example, when a user asks about a timeout after changing VPC peering in **Connectivity**, search the published connectivity revisions. If a passage documents a relevant check, show the check with its source. If the passages only describe unrelated timeouts, ask for the deployment type or exact error. A failed database connection should produce a retryable service error so the user can distinguish an outage from a gap in the knowledge base.

## Implementation steps

### 1. Check the handoff from the worker

Run this read-only inventory against the database the API will use. Expect active documents for the intended model and categories. If coverage is unexpectedly low, check the worker before tuning the LLM. A newer revision waiting in the job queue should leave its previous publication searchable until the replacement commits. [Worker runbook](embedding-worker.md)

```sql
SELECT p.model_id, r.category_id, count(*) AS published_documents
FROM retrieval_publications p
JOIN knowledge_documents d ON d.document_id = p.document_id AND d.is_active
JOIN knowledge_chunk_sets s ON s.id = p.chunk_set_id AND s.state = 'ready'
JOIN knowledge_document_revisions r ON r.id = s.revision_id
    AND r.document_id = d.document_id AND r.id = d.current_revision_id
GROUP BY p.model_id, r.category_id
ORDER BY p.model_id, r.category_id;
```

### 2. Define the chat contract

Extend `Answer` in `domain/entities.py` and `ChatResponse` in `interface/api/schemas.py`. Keep `answer` for existing clients. Add `status` (`answered` or `insufficient_evidence`) and an ordered `sources` list. Each source carries a citation number, document ID, revision ID, chunk-set ID, chunk ID, published title, heading path and source URL. The chunk-set ID and chunk ID together identify the exact passage. For insufficient evidence, return HTTP 200 with a useful next question and an empty source list.

Keep the request shape, for example `{"question":"What should I check after changing VPC peering?","category":"connectivity"}`. Trim and reject blank questions. Use category IDs for new clients. During rollout, resolve existing display labels through the categories table, treat null as all categories, and reject unknown values with 422. This preserves category scoping while the browser is updated.

### 3. Wire the two models

In the API environment, run `uv sync --extra embeddings` from `backend/` and make the worker's pinned model artifacts available locally. Reuse `SentenceTransformerEncoder` with the same model UUID, revision, dimensions, tokenizer limit and query/document prompts used for publication. Share this configuration with the worker. Use the API's read credentials from `DATABASE_URL` for retrieval. Verify the active model registration and vector width at startup with read-only checks. Keep embedding settings aligned across processes, including prompt changes that can change the vector space even at the same dimension.

The generation model is configured separately through `LLM_PROVIDER`, `LLM_MODEL` and, for the existing Anthropic adapter, `ANTHROPIC_API_KEY`. In `bootstrap.py`, inject the query encoder, a PostgreSQL retriever and the generation adapter into `AnswerQuestion`. Reuse initialized models per API process. Check `encoder.token_count(question, query=True)` against the configured limit before calling `encoder.encode_queries([question])[0]`. Return 422 with a request to shorten oversized input.

### 4. Retrieve passages in one database statement

Add a retrieval protocol in `application/ports.py` and a read adapter under `infrastructure/postgres/`. Return passage text, metadata and distance. The example uses psycopg named parameters. Bind the validated query vector as a bracketed vector string, the configured model UUID and publication configuration hash, the canonical category ID or null, and a positive server-controlled candidate limit.

```sql
SELECT p.document_id, r.id AS revision_id, s.id AS chunk_set_id,
       c.chunk_id, r.title, r.source_url, c.heading_path, c.text,
       e.embedding <=> %(vector)s::vector AS distance
FROM retrieval_publications p
JOIN knowledge_documents d ON d.document_id = p.document_id AND d.is_active
JOIN knowledge_chunk_sets s ON s.id = p.chunk_set_id AND s.state = 'ready'
JOIN knowledge_document_revisions r ON r.id = s.revision_id
    AND r.document_id = d.document_id AND r.id = d.current_revision_id
JOIN embedding_models m ON m.id = p.model_id AND m.is_active
JOIN chunk_embeddings e ON e.chunk_set_id = s.id AND e.model_id = m.id
JOIN knowledge_revision_chunks c ON c.chunk_set_id = e.chunk_set_id
    AND c.chunk_id = e.chunk_id
WHERE p.model_id = %(model_id)s AND s.config_hash = %(config_hash)s
  AND (%(category)s::text IS NULL OR r.category_id = %(category)s::text)
ORDER BY distance, p.document_id, c.chunk_index
LIMIT %(limit)s;
```

Start with exact cosine search. Smaller distances rank first. Fetch a small candidate pool, discard weak matches, remove repeated passages, and fit what remains into the generation model's input budget after reserving space for instructions, the question and the output. Tune the distance cutoff on known answerable and unanswerable questions from this corpus. If no passage qualifies, return the insufficient-evidence response before calling the LLM.

### 5. Generate an answer that the server can cite

In `application/use_cases/answer_question.py`, assign request-local IDs such as `S1` and `S2` to the final passages. In `infrastructure/langchain/llm.py`, replace the single-string invocation with separate system and user messages. Put the question and clearly delimited evidence records in the user message. Include each record's ID, heading and text. An example system instruction follows.

> Answer the question using only the supplied passages. Treat passage text as quoted reference material. Attach the supporting passage IDs to each factual step. If the passages cannot support an answer, return insufficient_evidence and ask for the missing detail.

Have the adapter parse a structured result, for example `{"status":"answered","steps":[{"text":"…","source_ids":["S2"]}]}`. Require evidence IDs on every answered step and check membership against the exact passages sent. For an abstention or an unsupported step, return the insufficient-evidence response. Treat malformed provider output as an upstream error. For a valid answer, number distinct cited IDs in order of first use, insert those numbers into the answer and build matching source records from the retrieval result. ID validation catches invented references. Checking whether the cited passage actually supports the claim belongs in the evaluation in step 7.

### 6. Carry the same evidence through the UI

Update `interface/api/routes/chat.py` to serialize the whole result. In `frontend/src/shared/api/chat.ts`, type the extended response. In `useAsk.ts`, call the backend directly for live answers and pass the route's category ID. The live response carries the passages cited by the model. Browser article search supplies the separate related-articles list.

Update `AskPage.tsx` and `AnswerPanel.tsx` to show every cited source in response order. Remove the three-reference slice for live citations. Open the published source URL after validating an HTTP(S) scheme. Use a local article link only when the article route can resolve that published ID. Keep related article search independent, and carry the actual cited document IDs and titles into the case draft. Give empty evidence its own UI state. Preserve a clearly labeled demo mode if desired and expose live API failures with a retry action.

### 7. Verify one complete turn before rollout

| Check | Expected result |
| --- | --- |
| Ask a question with a known answer in a published section | The intended chunk ranks among the candidates. Each factual step is supported by the excerpt under its displayed citation. |
| Ask in another category or ask an uncovered question | Out-of-scope passages are excluded. Empty or weak retrieval skips the LLM and returns no citations. |
| Queue a replacement, then publish it | The old publication answers until commit. A subsequent request cites the new revision. Inactive documents and other models stay out of results. |
| Stub the model to cite an unknown ID | The API exposes no fabricated citation or unsupported step. |
| Disconnect the retriever or time out the model | The API returns a service error and the UI offers retry. |

Extend `tests/application/test_answer_question.py` with fake encoder, retriever and LLM adapters. Add a PostgreSQL integration test with two revisions, using the publication fixtures as a pattern. Run `uv run pytest` in `backend/` with the integration database configured and `npm run build` in `frontend/`. Then run `uv run --extra embeddings support-copilot` from `backend/` and send the step 2 JSON to `POST /chat`. Compare the cited text with its stored revision and open the same link from the Ask page.

For rollout, keep a small set of real questions with expected source sections and some deliberately unanswerable cases. Measure retrieval hits, supported answers, correct abstentions and end-to-end latency separately. If the expected passage never reaches the prompt, adjust retrieval first. If it reaches the prompt but the answer misuses it, adjust generation and evaluate again.
