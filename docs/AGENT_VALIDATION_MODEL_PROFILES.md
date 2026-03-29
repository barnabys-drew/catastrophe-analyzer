# Agent Validation Model Profiles

These sample env profiles let Docker runs switch validator models/providers without code edits.

## Included samples

- `profiles/agent-validation/openai-gpt41mini.env.example`
- `profiles/agent-validation/openrouter.env.example`
- `profiles/agent-validation/xai-grok.env.example`
- `profiles/agent-validation/groq-llama.env.example`
- `profiles/agent-validation/ollama-local.env.example`
- `profiles/agent-validation/anthropic-claude.env.example`
- `profiles/agent-validation/google-gemini.env.example`

## Run with a profile

```bash
cp profiles/agent-validation/ollama-local.env.example .env.agent
docker compose --env-file .env.agent up -d --build
```

For cloud providers, copy the matching file to `.env.agent` and set your API key.

## Notes

- OpenAI/Groq/xAI/OpenRouter profiles call OpenAI-compatible `/chat/completions` endpoints directly.
- Anthropic/Gemini samples assume an OpenAI-compatible gateway endpoint.
- Ollama sample is tuned for a local host service on `host.docker.internal` (Docker Desktop/WSL2-friendly).
- All profiles use the shared rubric markdown at `docs/ENTITY_VALIDATION_RUBRIC.md`.
