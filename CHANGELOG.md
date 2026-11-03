# Changelog

## v1.0.0

First public release of the Project and Library recovery extension.

- Convert ChatGPT conversations to readable Markdown with a searchable local HTML interface.
- Automatically discover ChatGPT Projects from supported exports.
- Group Project conversations and Library files without requiring known Project names.
- Restore exported Library payloads, including images, documents, archives, and other original file contents.
- Reassemble multi-part/sharded payloads and verify restored file sizes where metadata is available.
- Recover Library files that are not associated with a Project.
- Provide archive-wide and per-Project Library views with filtering and sorting.
- Sort chats, Projects, and files by newest, oldest, A-Z, or Z-A; Library files can also be sorted by file type.
- Show human-readable Project date ranges using the oldest and newest recovered Project content dates.
- Allow Project display names to be renamed in the browser and exported as `project_names.json` for reuse.
- Preserve Project IDs, file IDs, origin references, and other recovery metadata in generated indexes.
- Display the tool version and GitHub repository link in the generated interface.
- Add synthetic regression coverage for modern and legacy conversation trees, Project discovery, Library recovery, duplicate filenames, and sharded payloads.
- Use platform-independent date sort keys so regression tests and generated ordering behave consistently on Windows, macOS, and Linux.
