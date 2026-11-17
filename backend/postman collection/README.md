# Postman collection

1. From `backend/`, install dependencies with `uv sync`, configure `.env` using
   `.env.example`, and start the API with `uv run support-copilot`.
2. In Postman, choose **Import** and select
   `Support Copilot.postman_collection.json` from this folder.
3. In the imported collection's **Variables** tab, set `base_url` if needed.
   It defaults to `http://127.0.0.1:8000`; omit the trailing slash.
4. Send **Health** first, then either **Chat** request. Each request includes
   response checks visible in Postman's test results.

The collection covers `GET /health` and `POST /chat`, including chat examples
with and without the optional `category`. Edit the JSON request body to change
the question or category. No API authentication is currently required.

Health works without an LLM or database. Chat requires `LLM_PROVIDER`,
`LLM_MODEL`, and `ANTHROPIC_API_KEY` in `backend/.env`. Keep provider credentials
on the backend; they do not belong in Postman. Chat calls the provider and does
not use retrieval yet. Running the entire collection sends two LLM requests.
