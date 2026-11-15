# Decisions

One line per decision: what we chose, why, and what we rejected. Newest last. Owner: Akshay (others add through their pull request text).

| # | Decision | Why | Rejected |
|---|---|---|---|
| D1 | Keep the working ticket-assistant layout; new parts go in agreed new files | No restructuring risk the night before the event | Moving everything into core/ and domain/ folders |
| D2 | Code decides; the LLM only writes; code checks every output | Fewer hallucinations, every answer traceable | Letting the LLM pick the outcome |
| D3 | Gate before any LLM call | No evidence, no answer; saves LLM calls | Asking the LLM to judge relevance |
| D4 | Hybrid search: BM25 + embeddings + RRF | Keywords catch error codes; embeddings catch paraphrases | Embeddings only |
| D5 | Calibrated logistic regression for classification | Honest probabilities, fast, explainable | kNN (overconfident), LLM classification |
| D6 | LLM chain: Gemini, then Groq, then extractive | The app never dies when a provider fails | One provider |
| D7 | Confidence = min(signals) | The weakest link decides | Averaging signals |
| D8 | Team rules are guidance, not locks; only force-push, reset --hard and reading .env are blocked | Nobody gets stuck pushing their own work | Per-person edit blocks |
