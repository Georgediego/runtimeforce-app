# RuntimeForce IDE

RuntimeForce is a local AI development environment for software engineering workflows, local/SSH workspaces, terminal operations, Git, and project memory.

## Privacy-first architecture

- The IDE runs locally on the user's computer.
- Prompts, source code, project context, workspace files, SSH credentials, local memory, and provider API keys stay on the user's computer.
- AI inference goes directly from the local IDE to the user's BYOK provider or local model runtime.
- The hosted RuntimeForce server is used for authentication, subscription status, dynamic plan entitlements, Creem billing, and account administration only.
- The server does not expose a Managed AI Proxy and does not store AI provider API keys.

## Dynamic plans

Plan codes and feature flags are database-driven and managed from the server Admin panel. The local app fetches verified entitlements from `GET /api/v1/billing/entitlements`; it does not use locally decoded JWT claims as proof of paid access. Feature keys are dynamic and can be enabled or disabled independently for each plan.

## Development

Install dependencies from `requirements.txt`, configure the local `.env`, and run:

```bash
python -m pytest -q
```

Use `python -m pytest` from the repository root so the local `app` package is importable. To start the IDE:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

After updating the local IDE service, restart it with:

```bash
sudo systemctl restart runtimeforce-app.service
```

See [Project Context](Project_Context.md) for architecture and development rules.
