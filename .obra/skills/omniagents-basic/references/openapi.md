# OpenAPI Integration

OmniAgents can generate agent tools from OpenAPI 3.x specifications. The `omniagents generate` commands produce tool files or MCP servers that integrate directly with the YAML agent loader.

## CLI: Generate Python Tools

The primary approach for YAML agents. Generates a Python file with `@function_tool` functions that are automatically discovered by the YAML loader.

```bash
omniagents generate openapi \
  --spec <path>              # Path to OpenAPI spec (YAML or JSON)
  --name <api_name>          # API name for env var prefix
  [--output <path>]          # Output file (default: tools/<name>_tools.py)
  [--include-tags TAG ...]   # Only operations with these tags
  [--exclude-operations OP ...]  # Exclude specific operationIds
  [--context-params PARAM ...]   # Path params injected from runtime context
  [--project <dir>]          # Project directory (default: cwd)
```

### What it generates

A Python module with:
- One `@function_tool` decorated function per API operation
- A `_request()` helper function for HTTP calls
- Environment variable configuration:
  - `{API_NAME}_BASE_URL` — API endpoint
  - `{API_NAME}_KEY` — API key
- Comprehensive docstrings with parameter constraints (enums, min/max, formats)
- Proper type annotations on all parameters

Example generated function:

```python
@function_tool
def get_pet_by_id(pet_id: int) -> str:
    """Find pet by ID.

    Returns a single pet.

    Args:
        pet_id: ID of pet to return. (required)
    """
    return _request("GET", f"/pet/{pet_id}")
```

### Using generated tools in agent.yml

Generated files go into `tools/` and are automatically discovered:

```bash
# Generate from spec
omniagents generate openapi --spec ebird_spec.yaml --name ebird

# This creates tools/ebird_tools.py with functions like:
#   get_data_obs_region_code_recent
#   get_ref_taxonomy_ebird
#   ... etc.
```

```yaml
# agent.yml — reference generated tools by name
name: Bird Expert
model: gpt-5.2
instructions_file: instructions.md
tools:
  - get_data_obs_region_code_recent
  - get_ref_taxonomy_ebird
  - lookup_species_code   # custom bridging tool
  - read_image             # builtin
```

```bash
# Set env vars and run
export EBIRD_BASE_URL="https://api.ebird.org/v2"
export EBIRD_KEY="your-api-key"
omniagents run -c agent.yml
```

### Context parameters

Path parameters can be injected from runtime context instead of being function arguments:

```bash
omniagents generate openapi \
  --spec spec.yaml \
  --name my_api \
  --context-params workspace_id
```

This removes `workspace_id` from the function signature and reads it from runtime context or a `{NAME}_WORKSPACE_ID` environment variable.

### Nested object flattening

Complex request bodies with nested objects are flattened into function parameters with underscore-separated names:

```json
{"guest": {"first_name": "...", "last_name": "..."}}
```

Becomes:

```python
def create_reservation(guest_first_name: str, guest_last_name: str) -> str:
```

The generated code reconstructs the nested structure before sending.

## CLI: Generate MCP Server

Generates a FastMCP server file. Useful for sharing API tools across multiple agents or running as a separate process.

```bash
omniagents generate mcp \
  --spec <path>              # Path to OpenAPI spec (YAML or JSON)
  --name <api_name>          # API name for env var prefix
  [--output <path>]          # Output file (default: <name>_mcp_server.py)
  [--server-name <name>]     # MCP server display name (default: API name)
  [--include-tags TAG ...]   # Only operations with these tags
  [--exclude-operations OP ...]  # Exclude specific operationIds
```

### What it generates

A FastMCP server file with:
- One `@mcp.tool` decorated async function per API operation
- `httpx.AsyncClient` for async HTTP requests
- Same env var configuration as the tools generator
- Entry point: `if __name__ == "__main__": mcp.run()`

### Using a generated MCP server in agent.yml

```bash
# Generate the server
omniagents generate mcp --spec petstore.yaml --name pet_api --server-name "Pet Store"
```

```yaml
# agent.yml
mcp_servers:
  - name: pet-api
    type: stdio
    params:
      command: python
      args: ["pet_api_mcp_server.py"]
      env:
        PET_API_BASE_URL: "https://api.example.com"
        PET_API_KEY: "${PET_API_KEY}"
```

## Choosing between generated tools and MCP servers

| | Generated tools | Generated MCP server |
|-|----------------|---------------------|
| **Integration** | Files in `tools/`, listed by name in `tools:` | Separate process, listed in `mcp_servers:` |
| **Customization** | Edit generated Python directly | Less customizable after generation |
| **Sharing** | Per-agent | Shared across multiple agents |
| **Best for** | Most cases — tight integration with YAML agents | Multi-agent setups, external integrations |

**Default choice: generated tools.** Use MCP servers when you need to share tools across agents or run the API bridge as a separate process.

## Type Mappings

OpenAPI types are mapped to Python in the generated code:

| OpenAPI Type | Format | Python Type |
|-------------|--------|-------------|
| `string` | — | `str` |
| `string` | `date`, `date-time`, `email`, `uri`, `uuid` | `str` |
| `integer` | — | `int` |
| `number` | — | `float` |
| `boolean` | — | `bool` |
| `array` | — | `List[ItemType]` |
| `object` | — | `Dict[str, Any]` |
