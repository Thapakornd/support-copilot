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
the question or category. Chat needs no authentication.

The frontend endpoints (`/me`, `/agents`, `/profile`, `/team`, `/articles`, `/tickets`) use the
demo identity header: set `DEMO_AUTH=true` (loopback `API_HOST` only), apply
`backend/sql/demo_identities.sql`, and set the `demo_user` variable to `customer`,
`mina`, `jordan`, `alex`, `priya` or `sam`. Without it they return 401.
The **Tickets** requests use the `ticket_id` variable (`SC-<number>`): send
**Tickets - create** as `customer`, copy the returned `id` into `ticket_id`, then
switch `demo_user` to `alex` to take, reply to or patch it.

Health works without an LLM or database. For chat, install and run with
`--extra embeddings` and configure the API database, pinned embedding model and
generation provider as described in the [backend setup guide](../README.md).
Chat searches published knowledge and calls the provider when it finds usable
evidence. The response includes `answer`, `status` and the ordered `sources`.
