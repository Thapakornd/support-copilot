# Support Copilot UI Design

## Intent

Support Copilot is a learning project for building a trustworthy, AI-first support experience for MongoDB-like product support. It should let a customer describe a technical problem, receive an answer grounded in approved documentation, and escalate to a human support case when the AI cannot resolve the issue.

The product is also a visible learning environment for LangChain, RAG, and LangGraph. The UI should make the important stages of that work understandable: what the customer asked, what sources informed the answer, what troubleshooting has already happened, and why a case was handed to human support.

## Goals

- Provide a focused, web-based support conversation for a customer with a MongoDB-related problem.
- Make AI the first line of assistance without making it a dead end.
- Show citations for every knowledge-based answer, so the customer can inspect the source material.
- Let a customer create a human-support ticket from a conversation at any time.
- Pre-fill escalation with a concise AI-generated case summary, relevant environment details, the conversation, sources consulted, and troubleshooting steps.
- Expose enough diagnostic information for the project owner to learn how LangChain/RAG/LangGraph decisions affect an answer, without exposing internal chain-of-thought to customers.

## Non-goals for the first UI

- A production MongoDB support portal, authentication system, SLA workflow, or real ticketing-system integration.
- Multi-agent orchestration beyond one support-assistant workflow and a human-handoff decision.
- Uploading or executing customer code, running live database diagnostics, or collecting telemetry automatically.
- Showing private model reasoning. The product may show short, structured reasons for a handoff, but never hidden reasoning traces.

## Primary user flow

1. A customer opens **New conversation** and describes an issue, optionally including product/version, driver/runtime, deployment type, error message, and sanitized logs.
2. The assistant asks targeted follow-up questions when essential context is missing.
3. It searches an approved knowledge base and replies with a practical diagnosis or next steps. Each response has citations to the documents used.
4. The customer either continues the conversation, marks the answer helpful, or chooses **Create support ticket**.
5. The assistant also recommends handoff when it has low confidence, finds no suitable source, has exhausted the supported troubleshooting path, detects a potentially urgent issue, or the customer asks for a human.
6. The ticket screen opens with a draft summary and all recoverable conversation context. The customer reviews/edits it and submits the case.
7. A confirmation screen displays the case ID and the case remains accessible in **My tickets**.

## Information architecture

### Global navigation

- **New conversation**: starts a customer support chat.
- **My tickets**: lists ticket drafts and submitted tickets.
- **Knowledge base**: optional browse/search view for the same approved documentation used by RAG.
- **Learning / run inspector**: developer-only area for observing the safe, structured workflow trace of a conversation.

For the first iteration, the global navigation may be a left sidebar on desktop and a compact drawer on mobile.

### New conversation screen

The default screen is a two-column support workspace.

- **Main column: conversation**
  - Page title: “Support assistant”.
  - A short expectation-setting line: “I’ll search approved documentation and help determine the next step.”
  - Customer and assistant message bubbles with time/order clarity.
  - Markdown support for code blocks and lists.
  - Per assistant answer: source citations, answer status, and feedback buttons (Helpful / Not helpful).
  - Composer with message entry, optional sanitized-log attachment placeholder, and Send button.
- **Context panel**
  - Editable issue profile: product area, deployment type, MongoDB version, driver/language, environment, severity, and error excerpt.
  - “What we have tried” checklist, built from customer and assistant messages but editable.
  - Current support status: `Investigating`, `Need more information`, `Suggested resolution`, or `Recommend human support`.
  - Persistent **Create support ticket** action.

The small-screen layout stacks the context panel below the conversation; the escalation action remains visible at the end of the assistant’s latest response and in the overflow menu.

### Citation behavior

Assistant answers must distinguish between:

- **Answer**: the practical explanation or steps.
- **Sources**: compact links with title, source type, and relevance snippet.
- **Limits**: when no reliable source supports a claim, the assistant says so and recommends clarification or escalation rather than presenting an unsupported answer as fact.

Clicking a citation opens a right-side detail panel or external documentation link. The UI should never imply that a citation proves a claim if the retrieved excerpt does not support it.

### Escalation and ticket draft

The first implementation uses a guided handoff rather than a blank ticket form.

When a customer selects **Create support ticket**, or the workflow recommends it, show a ticket-draft page or modal with:

- Clear heading: “Review your support case”.
- Handoff reason: customer-requested, insufficient information, no reliable knowledge-base match, unresolved after steps, or potential severity.
- Editable title and detailed description.
- AI-generated summary containing observed symptoms, environment, error excerpts, attempted steps, their outcomes, and unanswered questions.
- Attached conversation transcript and citations consulted, clearly labeled as support context.
- Severity selector (low, normal, high, critical) with explanatory text.
- A consent/confirmation checkbox acknowledging that supplied logs may be shared with support.
- `Back to chat`, `Save draft`, and `Submit ticket` actions.

On submission, display a generated case ID and status `Submitted`. A development stub may store tickets locally or through a FastAPI endpoint until a real ticketing provider is intentionally introduced.

### My tickets

A simple list supports learning and manual testing:

- Case ID, title, status, severity, created/updated date.
- Filters for Draft, Submitted, Waiting for customer, and Resolved.
- Clicking a ticket opens its saved summary, timeline, transcript, and related sources.

## Visual direction

Use a calm, technical support-product feel inspired by MongoDB’s clarity, without using MongoDB branding assets or claiming affiliation.

- Neutral light surface, dark readable text, green as the primary success/assistant accent, and amber/red only for warnings or escalation.
- Strong hierarchy: conversation is dominant; context and citations are quieter but discoverable.
- Accessible contrast, visible focus state, keyboard-operable controls, semantic message regions, and responsive layout.
- Avoid decorative dashboard density. The product should feel like a dependable support workspace, not a generic chatbot.

## UI states to design and implement

1. Empty conversation / suggested prompt.
2. Customer message pending.
3. Assistant is retrieving and composing (clear progress state; do not pretend it is “thinking”).
4. Assistant response with multiple citations.
5. Assistant requests missing information.
6. No reliable source found.
7. Recommended human handoff.
8. Customer-initiated handoff.
9. Editable ticket draft.
10. Ticket saved/submitted confirmation.
11. API/retrieval failure with retry and human-support fallback.

## Backend/UI contract (proposed)

Keep the current `POST /chat` endpoint as a thin prototype, then evolve it toward session-aware requests and structured responses. The UI should not need to know which LangChain or LangGraph component produced the response.

### Chat request

```json
{
  "conversation_id": "optional-id",
  "message": "Node.js requests time out after a network change",
  "issue_context": {
    "product_area": "Atlas networking",
    "mongodb_version": "8.0",
    "driver": "Node.js",
    "deployment_type": "replica set"
  }
}
```

### Chat response

```json
{
  "conversation_id": "generated-or-existing-id",
  "answer": "…",
  "citations": [
    { "id": "doc-1", "title": "Connection troubleshooting", "url": "https://…", "excerpt": "…" }
  ],
  "support_status": "need_more_information",
  "suggested_questions": ["Which Node.js driver version are you using?"],
  "handoff": {
    "recommended": false,
    "reason": null,
    "draft_summary": null
  }
}
```

### Ticket endpoints

- `POST /tickets/drafts`: creates or updates the pre-filled editable ticket draft.
- `POST /tickets/{ticket_id}/submit`: marks a draft as submitted; initially returns a generated case ID.
- `GET /tickets`: returns the customer’s local/demo tickets.
- `GET /tickets/{ticket_id}`: returns one ticket with its transcript and summary.

## RAG design for the learning project

Use RAG before considering complex agent behavior. Start with a small, versioned set of public MongoDB documentation pages or prepared local Markdown files. Preserve source URL, title, product/version scope, and chunk ID for every retrieved chunk.

Recommended initial sequence:

1. Ingest a small curated corpus into a vector store.
2. Retrieve the top relevant chunks for the customer message plus issue context.
3. Have the model answer only from retrieved material, cite it, and state when evidence is insufficient.
4. Log structured retrieval results, source IDs, and evaluation feedback in the developer-only inspector.
5. Add a test set of representative support questions, expected source documents, and cases that must escalate rather than guess.

The UI should be built against the structured citation/status contract above, with mock response data available until retrieval is implemented.

## LangChain and LangGraph guidance

Use LangChain first for model invocation, document loading/chunking, embeddings, vector-store retrieval, prompt templates, structured output, and evaluation helpers. This delivers the key learning goal without a graph yet.

Introduce LangGraph when the workflow has meaningful state and branching, rather than merely to wrap one prompt. A suitable first graph state contains conversation messages, issue context, retrieved sources, support status, troubleshooting steps, and handoff draft.

Suggested nodes:

1. **Capture context**: normalize message and issue profile.
2. **Retrieve knowledge**: search curated sources.
3. **Assess evidence**: determine whether the sources support an answer and whether more details are needed.
4. **Respond**: generate a cited, user-facing answer or targeted question.
5. **Evaluate handoff**: recommend a human ticket based on explicit, inspectable rules and user intent.
6. **Prepare ticket**: generate the editable summary only when escalation occurs.

Suggested transitions:

`Capture context → Retrieve knowledge → Assess evidence → Respond`

`Assess evidence → Request more information` when required context is missing.

`Assess evidence / Respond → Evaluate handoff → Prepare ticket` when a handoff is necessary or requested.

This keeps AI generation separate from workflow decisions. The handoff decision should be represented as structured fields and deterministic policy checks where possible, not as invisible model reasoning.

## Developer-only learning inspector

This is deliberately separate from the customer support screen and protected by a development-only flag. It can display:

- Input context sent to the workflow, with secrets and sensitive data redacted.
- Node sequence and duration.
- Retrieved document metadata, scores, and excerpts.
- Structured support status and handoff policy result.
- Final response and citations.
- Ticket summary inputs and output.

Do not show provider credentials, raw private logs, or model chain-of-thought. This view exists to teach observable system behavior, not to expose hidden reasoning.

## Acceptance criteria

- A user can start a conversation, send a message, and see a response or an honest failure state.
- Assistant answers render citations when provided by the API.
- A user can edit issue context and use it in later requests.
- A user can create a ticket from chat at any time.
- Ticket creation carries over an editable conversation-based summary, issue context, and attempted steps.
- A handoff recommendation is visibly explained with a user-safe reason.
- Ticket drafts and submitted tickets can be viewed in the demo UI.
- The UI is responsive and keyboard accessible.
- The frontend uses mock data/fixtures until the backend supplies the proposed response contract.
- The backend retains a minimal testable LangChain path before adding LangGraph branching.

## Implementation choices left to the builder

- **Product-owner call for v1:** use a demo, single-user identity and local/mock persistence. Real authentication and real ticket-provider integration remain out of scope.
- **Product-owner call for v1 priority:** build the chat, guided handoff, ticket draft, and My tickets screens first. Knowledge Base browsing and the developer Run Inspector are planned follow-on screens if capacity remains.
- Component library or custom component approach; the existing React/Vite project is the base.
- Vector database and embedding provider for the small initial corpus.
- Persistence mechanism for demo conversations/tickets.
- Exact route structure and whether ticket review is a route or modal.
- Authentication and authorization, intentionally deferred from this learning prototype.
