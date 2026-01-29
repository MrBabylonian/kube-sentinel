# KubeSentinel

An AI-powered autonomous SRE agent for Kubernetes incident remediation.

## Overview

KubeSentinel automatically detects, diagnoses, and fixes Kubernetes issues using LLM-powered reasoning and human-in-the-loop approval.

## Features

- **Autonomous Detection**: Scans namespaces for pod crashes, OOMKills, and failures
- **Root Cause Analysis**: Uses cluster inspection tools to diagnose issues
- **Safe Remediation**: Validates patches with dry-run before execution
- **Human Approval**: Requires explicit consent before applying changes
- **Verification Loop**: Confirms fixes resolved issues with retry logic
- **Structured Logging**: Full observability with structlog

## Architecture

```
agent → tools (inspect cluster) → validate (dry-run) → remediate (human gate) → verify → end/retry
```

## Requirements

- Python 3.12.12
- Kubernetes cluster access (kubeconfig or in-cluster)
- Google Cloud Vertex AI API key

## Installation

```bash
# Install dependencies
uv sync

# Set environment variables
export GOOGLE_VERTEX_API_KEY="your-key"
export GOOGLE_CLOUD_PROJECT="your-project"
```

## Usage

```bash
# Interactive mode
uv run python -m kube_sentinel.main run

# Specify namespace
uv run python -m kube_sentinel.main run --namespace production

# Custom prompt
uv run python -m kube_sentinel.main run --prompt "Fix OOMKilled pods"

# Verbose logging
uv run python -m kube_sentinel.main run --verbose
```

## Example Session

```
🚀 KubeSentinel Initialized (Namespace: default)
Goal: Scan namespace 'default' for issues and fix them

🤖 Agent: Listing pods to check for issues...
🤖 Agent: Found pod 'my-app-xxx' in CrashLoopBackOff. Investigating...
🤖 Agent: Diagnosis: OOMKilled - container exceeded memory limit (128Mi)

🛑 APPROVAL REQUIRED
Target: my-app
Action: Increase memory limit to 256Mi
Risk: low

Do you authorize this remediation? [y/n]: y
✅ Approved. Resuming...
🎉 Remediation executed successfully
✅ VERIFICATION SUCCESS: All pods are now healthy
```

## Test Scenario

Deploy the intentionally broken app:

```bash
kubectl apply -f manifests/my-app.yml
```

This creates a pod that tries to allocate 256MB but has a 128MB limit, triggering OOMKill. KubeSentinel will detect and fix it.

## Safety Features

- Dry-run validation before execution
- Human-in-the-loop approval gate
- Circuit breaker (max 3 verification attempts)
- Read-only operations until approval
- Comprehensive error handling

## Technology Stack

- **LangGraph**: Agent orchestration
- **Gemini 3 Pro**: LLM reasoning
- **kubernetes-asyncio**: Async K8s client
- **Pydantic**: Data validation
- **structlog**: Structured logging

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run linter
uv run ruff check .

# Run type checker
uv run mypy src/
```

## License

MIT

## Author

Bedirhan Gilgiler (MrBabylonian)
