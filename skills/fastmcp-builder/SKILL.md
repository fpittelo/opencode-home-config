---
name: fastmcp-builder
description: "Authoritative engineering guide for designing, building, containerizing, and testing Python FastMCP servers with Pydantic v2 validation, stdio/HTTP transports, and strict zero-warning quality gates for the HOME ecosystem."
---

# FastMCP Python Server Development Guide

This skill is the authoritative guide for engineering Model Context Protocol (MCP) servers in Python within the **HOME ecosystem**.
It enforces **Python >= 3.11 (default 3.12)**, `uv` package management, **FastMCP** (`mcp.server.fastmcp`), Pydantic v2 validation, asynchronous I/O (`asyncio`), multi-stage non-root Docker builds, and zero-warning TDD quality gates.

---

## 1. Project Initialization & Structure (`uv`)

Always initialize and manage Python MCP projects using `uv`:

```bash
# 1. Initialize project
uv init <service>-mcp
cd <service>-mcp

# 2. Add dependencies
uv add "mcp[cli]" pydantic httpx pytest pytest-asyncio pytest-cov ruff black isort mypy

# 3. Initialize Git repository
git init
```

### Standard Repository Structure:
```
<service>-mcp/
├── .github/
│   └── workflows/
│       └── ci.yml               # Zero-warning CI pipeline
├── src/
│   └── <service>_mcp/
│       ├── __init__.py
│       ├── server.py            # FastMCP initialization & tool definitions
│       ├── models.py            # Pydantic v2 input & output schemas
│       ├── client.py            # Async HTTP client / upstream API integration
│       └── utils.py             # Response formatting (Markdown/JSON) & error handlers
├── tests/
│   ├── conftest.py              # Test fixtures & mock servers
│   ├── test_models.py           # Schema validation tests
│   └── test_server.py           # FastMCP tool execution tests
├── Dockerfile                   # Multi-stage non-root container
├── .dockerignore
├── pyproject.toml               # Project metadata & tool configs (ruff, mypy, pytest)
└── README.md
```

---

## 2. Server Architecture & Transport Protocols

Initialize the server using `FastMCP` from `mcp.server.fastmcp`:

```python
from mcp.server.fastmcp import FastMCP

# Standard naming: <service>_mcp
mcp = FastMCP(
    name="service_mcp",
    instructions="Authoritative description of server purpose and domain capabilities."
)
```

### Transport Options:
1. **`stdio` (Default for local agent tooling & Docker containers):**
   ```python
   if __name__ == "__main__":
       mcp.run()
   ```
2. **`streamable-http` / SSE (For network-bridged services):**
   ```python
   if __name__ == "__main__":
       mcp.run(transport="streamable_http", host="0.0.0.0", port=8000)
   ```

---

## 3. Tool Implementation & Pydantic v2 Validation

### Naming Conventions:
- Tool names must use `snake_case` prefixed with service domain (e.g., `intervals_get_wellness`, `github_create_issue`, `home_query_finance`).

### Pydantic v2 Schema Definition:
```python
from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field, field_validator, ConfigDict

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"

class QueryInput(BaseModel):
    '''Input parameters for querying service records.'''
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid"
    )

    query: str = Field(..., description="Search query string", min_length=2, max_length=100)
    limit: int = Field(default=20, description="Max results to return (1-100)", ge=1, le=100)
    offset: int = Field(default=0, description="Pagination offset", ge=0)
    format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN, description="Output format")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Query string cannot be empty or whitespace only")
        return v.strip()
```

### Tool Registration Pattern:
```python
@mcp.tool(
    name="service_query_records",
    annotations={
        "title": "Query Service Records",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def service_query_records(params: QueryInput) -> str:
    '''Search and retrieve records from the service.

    Args:
        params (QueryInput): Validated input parameters.

    Returns:
        str: Formatted Markdown table or JSON string of results.
    '''
    try:
        data = await fetch_upstream_records(query=params.query, limit=params.limit, offset=params.offset)
        if params.format == ResponseFormat.JSON:
            return json.dumps(data, indent=2)
        return format_records_markdown(data)
    except Exception as e:
        return handle_tool_error(e)
```

---

## 4. Advanced FastMCP Capabilities

### Context Injection (Logging & Progress)
```python
from mcp.server.fastmcp import Context

@mcp.tool()
async def long_running_sync(dataset_id: str, ctx: Context) -> str:
    await ctx.report_progress(0.1, "Initializing sync...")
    await ctx.log_info(f"Syncing dataset {dataset_id}")
    # Process...
    await ctx.report_progress(1.0, "Sync complete.")
    return f"Dataset {dataset_id} synchronized successfully."
```

### Resources & Prompts
```python
@mcp.resource("config://settings/{section}")
async def get_config_section(section: str) -> str:
    '''Expose read-only configuration schemas as MCP resources.'''
    return json.dumps(load_config_section(section))

@mcp.prompt()
def review_code_prompt(code_snippet: str) -> str:
    '''Provide reusable agent prompt templates.'''
    return f"Please review the following Python code for PEP 8 compliance:\n\n```python\n{code_snippet}\n```"
```

### Lifespan Resource Management (Databases & HTTP Clients)
```python
from contextlib import asynccontextmanager
import httpx

@asynccontextmanager
async def app_lifespan():
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield {"http_client": client}

mcp = FastMCP("service_mcp", lifespan=app_lifespan)
```

---

## 5. Multi-Stage Non-Root Docker Architecture

Every HOME MCP server publishes a security-hardened container to GitHub Container Registry (`ghcr.io/fpittelo/<repo>:<tag>`):

```dockerfile
# Multi-stage build for Python FastMCP
FROM python:3.12-slim AS builder

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv build

# Runtime Stage
FROM python:3.12-slim AS runtime

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -s /bin/bash -m appuser

COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /app/src /app/src

USER appuser

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import socket; sys.exit(0)"

ENTRYPOINT ["python", "-m", "service_mcp.server"]
```

---

## 6. Pre-Flight & CI Quality Gates

Before opening a PR, the code must pass the standardized zero-warning pre-flight gate locally:

```bash
# 1. Lint & Formatting
ruff check . && black --check . && isort --check-only .

# 2. Strict Type Checking
mypy --strict src/

# 3. Unit Tests with Zero Warnings
pytest -W error --cov=src/ tests/
```

---

## 7. Testing & Evaluation Framework

### FastMCP Unit Testing with `pytest-asyncio`:
```python
import pytest
from service_mcp.models import QueryInput, ResponseFormat
from service_mcp.server import service_query_records

@pytest.mark.asyncio
async def test_service_query_records_success(mock_upstream_api):
    params = QueryInput(query="test_query", limit=10, format=ResponseFormat.JSON)
    result = await service_query_records(params)
    assert "test_query" in result
```

### Local MCP Inspector Testing:
```bash
uv run mcp dev src/<service>_mcp/server.py
```

---

## Reference Library

Detailed reference guides located in `./reference/`:
- **[Python FastMCP Reference](./reference/python_mcp_server.md)** — Comprehensive code patterns, Pydantic models, and error handlers.
- **[MCP Universal Best Practices](./reference/mcp_best_practices.md)** — Core protocol design rules and tool naming.
- **[Evaluation Harness](./reference/evaluation.md)** — Designing 10-question evaluation sets and running automated benchmarks.
