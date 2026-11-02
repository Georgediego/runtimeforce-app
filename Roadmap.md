# RuntimeForce IDE Roadmap

This roadmap describes possible product improvements. Items are plans, not guarantees or delivery commitments.

## Available today

- Local-first AI development environment with local and SSH workspaces.
- BYOK cloud providers and supported local model runtimes.
- Integrated editor, terminal, Git workflows, and project context.
- Local project memory and workspace data.
- Server-backed account authentication, dynamic plan entitlements, and billing.
- GitHub account linking and repository selection through RuntimeForce account services.
- Social Drafts for reviewing and publishing content to a connected X account.

## Next priorities

1. Close remaining authentication and local API security gaps.
2. Improve first-run setup and installation documentation across Linux, macOS, and Windows.
3. Add automated CI checks for Python tests and frontend assets.
4. Improve local backup, restore, and credential recovery guidance.
5. Expand integration coverage while keeping user project data and BYOK credentials local.

## Product principles

- Keep source code, prompts, workspace files, SSH credentials, BYOK keys, and local memory on the user's computer.
- Keep account, subscription, entitlement, billing, and connected social OAuth responsibilities on the hosted control plane.
- Prefer a small, maintainable application over unnecessary services or infrastructure.
- Publish only capabilities that are implemented and verified.
