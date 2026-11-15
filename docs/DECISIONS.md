# Decisions

One line per decision: what we chose, why, and what we rejected. Newest last. Owner: Akshay (others add through their pull request text).

| # | Decision | Why | Rejected |
|---|---|---|---|
| D1 | Split code into `core/` (any problem) and `domain/` (this problem) | On the day we only write the domain pack | One big app per problem |
| D2 | Code decides; the LLM only writes; code checks every output | Fewer hallucinations, every answer traceable | Letting the LLM pick the outcome |
| D3 | Evidence gate before any LLM call | No evidence, no answer; saves LLM calls | Asking the LLM to judge relevance |
| D4 | Hybrid search: BM25 + embeddings + RRF | Keywords catch error codes; embeddings catch paraphrases | Embeddings only |
| D5 | Calibrated logistic regression for classification | Honest probabilities, fast, explainable | kNN (overconfident), LLM classification |
| D6 | LLM chain Gemini, then Groq or Ollama, then extractive | The app never dies when a provider fails | One provider |
| D7 | Confidence = min(signals) | The weakest link decides | Averaging signals |
