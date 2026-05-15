# skill-channel-zalo

Standalone Zalo channel gateway service repo.

## Responsibility

This repo owns the Zalo gateway boundary as a service skill. Core should call it only through the service contract declared in `skill.yaml`.

Capabilities declared in `skill.yaml`:

- `channel_gateway.zalo_status`
- `channel_gateway.zalo_webhook`

## Contract

- Mode: `service`
- Entrypoint: `src.skill_channel_zalo_service.app:app`
- Healthcheck: `http://127.0.0.1:8422/health`
- Execute endpoint: `http://127.0.0.1:8422/execute`
- Manifest endpoint: `http://127.0.0.1:8422/manifest`
- Core API compatibility: `>=1.0,<2.0`

## Permissions

- `external_actions: true`
- `internet_access: true`
- `file_write: true`
- `read_memory: false`
- `write_memory: true`

## Integration rule

Core integration must stay at the service boundary defined by `skill.yaml`. Core should not keep Zalo webhook or auth logic on its main path once this service is configured.
## Verification

- Recommended command: `python -m pytest -q`
- Current minimum coverage: manifest and contract smoke tests inside `tests/`

## Implementation status

This repo already owns the Zalo gateway service boundary. A temporary fallback may still exist during rollout, but the stable integration path is the HTTP contract exposed by this repo.

Current dependency note: the service still resolves the core repo location, so implementation independence is not complete yet.
