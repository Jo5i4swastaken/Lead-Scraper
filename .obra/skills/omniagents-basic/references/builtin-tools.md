# OmniAgents Builtin Tools — Parameter Reference

## File Operations

### read_file
Read file contents with line numbers and smart truncation.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | required | Path to the file to read |
| `start_line` | int | 1 | 1-based line number to start from |
| `num_lines` | int | 2000 | Maximum lines to read |
| `mode` | str | "slice" | "slice" (line range) or "indentation" (smart block extraction) |
| `anchor_line` | int | None | For indentation mode: line to expand around |
| `max_levels` | int | None | For indentation mode: max parent levels (0 = unlimited) |
| `include_siblings` | bool | False | For indentation mode: include sibling blocks |
| `include_header` | bool | True | For indentation mode: include header comments |

### write_file
Create or overwrite a file.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | required | Path to the file to write |
| `content` | str | required | Content to write |
| `append` | bool | False | Append instead of overwrite |

### edit_file
Targeted find-and-replace edits.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_path` | str | required | Path to the file to edit |
| `old_text` | str | required | Text to replace (literal by default) |
| `new_text` | str | required | Replacement text |
| `expected_replacements` | int | None | Fail unless exactly this many replacements |
| `max_replacements` | int | None | Limit number of replacements |
| `start_line` | int | None | Restrict to range (inclusive) |
| `end_line` | int | None | Restrict to range (inclusive) |
| `dry_run` | bool | False | Preview diff without writing |
| `regex` | bool | False | Treat old_text as regex |

### apply_patch
Apply multi-file patches in a custom AI-friendly format.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `patch` | str | required | Patch contents in `*** Begin Patch` / `*** End Patch` format |

Patch format supports `*** Add File:`, `*** Update File:`, and `*** Delete File:` operations with `+`/`-`/` ` line prefixes and `@@` context headers.

### glob_files
Find files by glob pattern.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | str | required | Glob pattern (e.g., `"*.py"`, `"**/*.json"`) |
| `path` | str | workspace root | Directory to search in |
| `ignore_hidden` | bool | False | Exclude hidden files/dirs |
| `respect_gitignore` | bool | True | Exclude gitignored paths |

### grep_files
Search file contents with regex.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | str | required | Regex pattern to search for |
| `path` | str | workspace root | Directory or file to search |
| `include` | str | None | Glob filter for files (e.g., `"*.py"`) |
| `limit` | int | 100 | Max files to return (max 2000) |
| `timeout` | int | 30 | Max search time in seconds |
| `ignore_hidden` | bool | False | Exclude hidden files/dirs |
| `respect_gitignore` | bool | True | Exclude gitignored paths |

### list_directory
List directory tree.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | str | required | Directory to list |
| `offset` | int | 1 | 1-based entry to start from |
| `limit` | int | 50 | Max entries to return |
| `depth` | int | 2 | Max traversal depth (min 1) |
| `ignore_hidden` | bool | False | Exclude hidden files/dirs |
| `respect_gitignore` | bool | True | Exclude gitignored paths |

## System Operations

### execute_bash
Run shell commands.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `command` | str | required | Shell command to execute |
| `timeout` | int | 30 | Max execution time in seconds |
| `cwd` | str | None | Working directory |
| `max_output_chars` | int | 40000 | Max output characters |

## Web & Search

### download_file
Download files from URLs.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | required | URL to download |
| `output_path` | str | None | Save path (auto-generates temp path if omitted) |

### web_search
Google search via SerpAPI.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search query |
| `num_results` | int | 10 | Number of results (max 100) |
| `include_news` | bool | False | Include news results |
| `time_period` | str | None | `"past_day"`, `"past_week"`, `"past_month"`, `"past_year"` |

### scholar_search
Google Scholar search.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search query |
| `num_results` | int | 10 | Number of results (max 20) |
| `sort_by` | str | "relevance" | `"relevance"` or `"date"` |
| `publication_date` | str | None | `"since_2023"`, `"since_2020"`, `"since_2017"`, `"since_2014"` |
| `author` | str | None | Filter by author |

### youtube_search
YouTube video search.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search query |
| `num_results` | int | 10 | Number of results (max 100) |
| `sort_by` | str | "relevance" | `"relevance"`, `"upload_date"`, `"view_count"`, `"rating"` |
| `upload_date` | str | None | `"last_hour"`, `"today"`, `"this_week"`, `"this_month"`, `"this_year"` |
| `duration` | str | None | `"short"` (<4min), `"medium"` (4-20min), `"long"` (>20min) |

## Display

### display_artifact
Display rich content in the UI.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `title` | str | required | Display label |
| `content` | str | None | Raw content to display |
| `path` | str | None | File path to display |
| `mode` | str | "markdown" | `"markdown"`, `"html"`, `"image"`, `"pdf"`, `"docx"`, `"pptx"` |
| `artifact_id` | str | None | Pass existing ID to update in place |

## Image

### read_image
Read images for LLM vision processing.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `image_path` | str | required | Path to image file |
| `detail` | str | "auto" | `"low"`, `"high"`, or `"auto"` |

Supports PNG, JPEG, GIF, WebP, BMP.
