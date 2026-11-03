# Attribution and modifications

This repository is intended as a fork/derivative of:

**marelucent/chatgpt-export-reader**  
https://github.com/marelucent/chatgpt-export-reader

The upstream project is distributed under the MIT License; the upstream `LICENSE` text is retained unchanged.

Project-recovery additions in this derivative include:

- automatic discovery of `g-p-*` ChatGPT Project identifiers
- conversation membership via `conversation_template_id`
- Library membership via `gizmo_id`
- `library_files.json` indexing
- `export_manifest.json` logical-to-physical payload resolution
- restoration of `file_id.dat` payloads under original filenames
- duplicate-name protection and size verification
- multi-part payload reconstruction
- per-Project HTML and JSON indexes
- optional Project-name override mapping
- schema/recovery reporting
- synthetic regression tests for Project recovery
- global Library browsing, filtering, and payload access
- browser-local Project renaming with exportable name mappings
- Project date ranges and client-side sorting controls

These additions were developed from observed 2026 ChatGPT export structures. They should not be interpreted as an official OpenAI export-format specification.
