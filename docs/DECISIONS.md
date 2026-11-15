# Decisions

One line per decision: what we chose, why, and what we rejected. Newest last. Anyone can add one in their pull request.

| # | Decision | Why | Rejected |
|---|---|---|---|
| D1 | Keep the working ticket-assistant layout; new parts go in agreed new files | No restructuring risk the night before the event | Moving everything into core/ and domain/ folders |
| D2 | Code decides; the LLM only writes; code checks every output | Fewer hallucinations, every answer traceable | Letting the LLM pick the outcome |
| D3 | Gate before any LLM call | No evidence, no answer; saves LLM calls | Asking the LLM to judge relevance |
| D4 | Hybrid search: BM25 + embeddings + RRF | Keywords catch error codes; embeddings catch paraphrases | Embeddings only |
| D5 | Calibrated logistic regression for classification | Honest probabilities, fast, explainable | kNN (overconfident), LLM classification |
| D6 | LLM chain: Gemini, then Groq, then extractive | The app never dies when a provider fails | One provider |
| D7 | Confidence = min(signals) | The weakest link decides | Averaging signals |
| D8 | Rules are guidance; anyone can edit, push and merge; only force-push and reading .env are blocked | Nobody gets stuck waiting for someone else | Per-person edit, push or merge blocks |
