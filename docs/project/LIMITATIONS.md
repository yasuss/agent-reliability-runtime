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
- Apache-2.0 licensing applies. The historical v1 release remains immutable.
  Version 2.0.0 is a code/docs/runtime packaging release; its reviewed Vite patch
  affects development/build tooling and does not require replacing the unchanged
  static evidence deployment.
- The v2 public Python extension boundary is `core.ports` and its neutral value
  contracts. Internal import paths changed; the CLI/MCP/script entry points remain.
- Reconciler, TimerStore, SourceRevisionReader and CapabilityRegistry are planned
  interfaces only. PARTIAL is a verification value, not new OpsDesk behavior.
- Dependency extras and a generic control plane are deferred.
- The unauthenticated v1 API is supported only on loopback by default. Do not bind
  it to `0.0.0.0`, a LAN interface, or a public interface without an external
  trust/authentication boundary.

Supported local startup is:

```text
uv run uvicorn agent_reliability_runtime.demo.api:app --host 127.0.0.1 --port 8000
```

The v1 API has no authentication boundary. Do not bind it to `0.0.0.0`, a LAN interface, or a public interface without an external trust/authentication boundary.
