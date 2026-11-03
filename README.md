# ChatGPT Export Reader + Project Recovery

A local recovery tool for ChatGPT data exports.

> **Version:** 1.0.0  
> **Repository:** https://github.com/rschaer/chatgpt-export-reader


It turns the raw export into a readable archive of your chats and, on supported newer exports, also reconstructs **Projects** and restores **Library files** such as documents, images, ZIP archives, PDFs, and other uploaded or generated files.

This project is based on [marelucent/chatgpt-export-reader](https://github.com/marelucent/chatgpt-export-reader) and keeps its simple idea: your export should become something you can actually browse and keep on your own computer.

The Project and Library recovery extension in this fork was developed with assistance from **ChatGPT 5.6**, including reverse-engineering the 2026 export relationships, implementation, and test development. The resulting code was tested against synthetic fixtures and a real exported archive before publication.

## What this tool gives you

After conversion, you get a local web interface that you can open in any normal browser. It has three main sections:

- **All chats** — every recovered conversation in one searchable list.
- **Projects** — chats and Library files grouped back into the ChatGPT Project they belonged to, when that information exists in the export.
- **Library** — one searchable view of all Library files across the whole export, including files attached to Projects and files with no Project association.

The tool also:

- converts conversations into individual Markdown files;
- restores Library file contents from the opaque `.dat` files found in newer ChatGPT exports;
- restores the original filename and extension where possible;
- recovers images and other binary files as well as text documents;
- keeps duplicate filenames without overwriting one copy with another;
- shows the oldest-to-newest date range for each recovered Project;
- lets you sort chats and files by newest, oldest, A–Z, or Z–A;
- lets you sort Library files by file type/extension;
- lets you filter the Library to all files, Project files, unassigned files, or selected Projects;
- lets you rename generic recovered Project names in the web interface;
- preserves detailed recovery metadata in JSON index files;
- runs entirely on your own computer and does not upload your archive anywhere.

The original ChatGPT export is not modified.

## Requirements

You need:

- Python 3.6 or newer;
- an unzipped ChatGPT data export;
- no extra Python packages.

Check Python with:

```text
python --version
```

On some macOS or Linux systems the command is `python3` instead.

## Quick start

### 1. Fully unzip your ChatGPT export

Newer exports may contain many files such as:

```text
conversations-000.json
conversations-001.json
library_files.json
export_manifest.json
file_00000000....dat
...
```

Keep them together in the same export directory.

### 2. Put `convert.py` in the export directory

For example on Windows:

```text
C:\ChatGPT-Backup\
    convert.py
    conversations-000.json
    conversations-001.json
    library_files.json
    export_manifest.json
    file_....dat
```

You can also keep `convert.py` somewhere else and give it the path to the export directory.

### 3. Run the converter

From the export directory:

```powershell
python .\convert.py
```

Or on macOS/Linux:

```bash
python3 convert.py
```

To specify the export folder explicitly:

```bash
python convert.py /path/to/unzipped-export
```

### 4. Open the recovered archive

When conversion finishes, the console prints the exact location of the generated web interface. By default it is:

```text
conversations/INDEX.html
```

Open `INDEX.html` in your browser. No web server is required.

## Using the web interface

### All chats

The **All chats** tab contains all recovered conversations. You can search them and sort them by:

- newest first — the default;
- oldest first;
- name A → Z;
- name Z → A.

Each conversation also exists as a normal `.md` file in the generated archive directory, so the archive does not depend on the HTML interface.

### Projects

The **Projects** tab groups chats and Library files using the Project relationship stored in the ChatGPT export.

For each Project the interface shows:

- conversation count;
- Library-file count;
- Project ID;
- **date range**, from the creation date of the oldest recovered chat or Library item to the newest.

This date range can help identify Projects whose names were not preserved by the export.

Project lists can also be sorted by newest, oldest, A–Z, or Z–A.

#### Renaming Projects

Some ChatGPT exports preserve the Project relationship but not the human-readable Project name. In that case the tool creates a stable generic name such as:

```text
Project_01_g-p-6a8019b1
```

Use **Rename** in the Projects view to give it a meaningful display name.

Because `INDEX.html` is a normal local file, a browser is not allowed to silently rename folders on your disk. The new name is therefore stored locally by the browser for display.

To make the names permanent for future recovery runs, click:

**Export project_names.json**

Save that file beside the original ChatGPT export and run the converter again. The recovered folders and indexes will then use those names.

You can also edit `project_names.example.json` manually and save it as `project_names.json` beside the export.

### Library

The **Library** tab is a catalog of every Library record found in the export.

You can show:

- all Library files;
- all files associated with Projects;
- only files with no Project association;
- one particular Project;
- any combination of Projects and unassigned files.

You can search by filename, file ID, Project, state, recovery status, or file type.

Library lists can be sorted by:

- newest first — the default;
- oldest first;
- filename A → Z;
- filename Z → A;
- file type A → Z, using the file extension such as `.md`, `.pdf`, `.png`, `.zip`, and so on.

### Where the recovered Library files are

The web interface is only an index. The recovered files themselves are ordinary files on disk and can be opened, copied, backed up, or searched with any normal file manager.

Project files are stored under:

```text
conversations/
    Projects/
        <Project name>/
            Files/
```

Library files that do not belong to a Project are stored under:

```text
conversations/
    Library/
        Files/
```

The dedicated Library page is:

```text
conversations/Library/INDEX.html
```

and the full Library metadata catalog is:

```text
conversations/Library/library_index.json
```

## Example recovered layout

```text
conversations/
├── INDEX.html
├── recovery_report.json
├── project_names.example.json
├── 20261001_Example chat.md
├── 20261002_Another chat.md
│
├── Library/
│   ├── INDEX.html
│   ├── library_index.json
│   └── Files/
│       └── unassigned-note.txt
│
└── Projects/
    ├── INDEX.html
    ├── Project_01_g-p-abc123/
    │   ├── INDEX.html
    │   ├── library_index.json
    │   └── Files/
    │       ├── notes.md
    │       ├── photo.png
    │       └── source-package.zip
    └── Project_02_g-p-def456/
        ├── INDEX.html
        ├── library_index.json
        └── Files/
```

## Useful command-line options

Choose a different output directory:

```bash
python convert.py /path/to/export --output /path/to/recovered-archive
```

Use a particular Project-name mapping:

```bash
python convert.py /path/to/export --project-names /path/to/project_names.json
```

Build the indexes without copying/reassembling Library payloads:

```bash
python convert.py /path/to/export --no-library-files
```

`--no-project-files` is kept as an alias for the same option.

## Important backup advice

Keep the original ChatGPT export unchanged even after recovery succeeds.

This tool creates a convenient reconstructed copy, but the original export remains the best source if the recovery logic is improved later or OpenAI changes the export format again.

Your export may contain private conversations, documents, images, and other sensitive material. Do not commit your personal export or recovered archive to a public Git repository.

---

# Technical details

The rest of this README explains how the recovery works. You do not need this section just to use the tool.

## Project detection

In the 2026-era export format this tool was built against, Project membership can be reconstructed from a shared `g-p-*` identifier.

A conversation can contain:

```text
conversation_template_id = g-p-...
```

A Project Library record can contain:

```text
gizmo_id = g-p-...
```

When those IDs match, the conversation and Library record belong to the same Project.

The recovery does **not** depend on knowing the Project's displayed name or on searching for Project-specific words inside chats or filenames.

## Library payload recovery

`library_files.json` contains metadata such as:

- original filename;
- `file_id`;
- extension and MIME type;
- Project `gizmo_id`;
- size;
- state and visibility;
- creation/modification dates;
- version/provenance data;
- originating thread/message IDs.

The actual file bytes may be stored in the export under an opaque name such as:

```text
file_000000002db881f5b324ab6f0ba927c5.dat
```

`export_manifest.json` maps the logical file to one or more physical payload files. The tool copies or reassembles those payloads and writes them using the original filename and extension from `library_files.json`.

The `.dat` suffix is therefore an export-storage filename; it does not mean the recovered file contents were converted to a proprietary format.

## Sharded files

Some logical files can be represented by multiple payload parts in the manifest. The tool joins them in the order specified by `export_manifest.json` and verifies the final size when `file_size_bytes` is available.

## Duplicate filenames

If two Library records have the same original filename, neither is overwritten. The later collision receives an ID-derived suffix so both payloads survive.

## Date ranges and sorting

Project artifact ranges use all available creation dates from:

- Project conversations; and
- Project Library records.

The earliest and latest of those timestamps form the displayed Project date range.

Generated HTML lists carry sortable metadata and are initially written newest-first. Sorting in the browser only changes the display order; it does not rename or modify recovered files.

Library file-type sorting uses a normalized lowercase extension, including the leading dot where an extension is available.

## Recovery metadata and reporting

Per-Project `library_index.json` files and the global `Library/library_index.json` preserve the metadata used during recovery plus fields such as:

- restored filename;
- manifest parts;
- sharded/not-sharded state;
- restore status;
- size-verification result;
- originating recovered conversation filename when it can be linked.

`recovery_report.json` records the detected schema, Project counts, Library counts, recovered-payload counts, and discrepancies such as Projects that appear only on one side of the export.

## Compatibility and limitations

The tool supports:

- a single `conversations.json`;
- chunked `conversations-000.json`, `conversations-001.json`, ...;
- older conversation trees with explicit `children` arrays;
- newer conversation trees reconstructed from `parent` pointers;
- exports without Project/Library metadata, where ordinary chat conversion still works;
- the observed 2026 Project/Library schema described above.

OpenAI's export format is not a documented stable API and may change. The tool therefore treats the current structure as an observed schema rather than assuming it will remain valid forever.

A human-readable Project name may not be present in the export. That is why the recovery process uses stable Project IDs and supports user-supplied names separately.

## Testing

Run the included synthetic tests with:

```bash
python test_convert.py
```

The test data contains no personal ChatGPT export content. It covers conversation-tree compatibility, chunked exports, automatic Project detection, Project/Library association, file restoration, duplicate filenames, sharded payloads, unassigned Library recovery, date ranges, sorting controls, Project renaming UI generation, and recovery reports.

## Privacy

The converter uses Python's standard library and performs local file operations only. It does not require an account, API key, network request, or external service.

## Upstream and license

This fork is based on **ChatGPT Export Reader** by marelucent:

https://github.com/marelucent/chatgpt-export-reader

The upstream project is MIT licensed. See `LICENSE`, `NOTICE.md`, and `UPSTREAM_BASE.md` for attribution and base-version information.
