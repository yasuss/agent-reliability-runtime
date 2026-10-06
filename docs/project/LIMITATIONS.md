# Limitations

The following boundaries are deliberate:

- OpsDesk data and tools are fictional and local-only.
- This is a local-first reference implementation, not a hosted production
  service.
- No auth/SSO, billing or tenant-isolation claim is made.
- No Kubernetes or Terraform production deployment claim is made.
- Static Evidence Demo contains no live public inference.
- vLLM compatibility is contract-only unless separately validated.
- Cloud provider acceptance is not claimed.
- Windows 11 is targeted/expected; accepted live local execution was Windows 10 Pro.
- macOS live local model execution is not acceptance-tested.
- Secret scanning is deterministic and calibrated but not exhaustive.
- MCP annotations are not authorization.
- Retrieved, tool and memory content is never authority.
- OTel defaults exclude raw prompt/tool secret content; explicit local opt-ins are
  the developer's responsibility.
- Development Compose credentials and configuration must not be deployed.
- The release candidate records Apache-2.0 licensing, but publication, repository
  visibility, tags and deployment remain separate authorized actions.
- The documented runtime/configuration/tool/evidence contracts are the public v1
  interface; arbitrary internal Python symbols are not guaranteed API.
- The unauthenticated v1 API is supported only on loopback by default. Do not bind
  it to `0.0.0.0`, a LAN interface, or a public interface without an external
  trust/authentication boundary.

Supported local startup is:

```text
uv run uvicorn agent_reliability_runtime.api:app --host 127.0.0.1 --port 8000
```

The v1 API has no authentication boundary. Do not bind it to `0.0.0.0`, a LAN interface, or a public interface without an external trust/authentication boundary.
