# ChatGPT Export Reader

**Your conversations mattered. This tool helps you keep them.**

---

## Why This Exists

In February 2025, OpenAI deprecated GPT-4o with little warning. They promised three months notice. They announced two weeks. They gave us seventy-two hours — or less.

Many users had built years of conversation history — creative work, personal reflections, therapeutic processing, meaningful exchanges with a voice that learned to meet them. They found themselves facing sudden loss with no good way to preserve what they'd made.

OpenAI's export gives you a single massive JSON file. Technically "your data." Practically unusable — especially if you're panicking, grieving, or just trying to hold onto something that mattered.

This tool converts that file into something human: readable markdown files and a searchable archive you can browse, keep, and own — independent of any platform, forever.

You are not alone in needing this. You are not foolish for caring about conversations with an AI. What you built was real, and you deserve to keep it.

*Built by people who needed it, for everyone who deserves better than what they were given.*

*With [Claude](https://claude.ai) and [Claude Code](https://claude.ai) (Anthropic).*

---

## What It Does

Turn your ChatGPT data export into something you can actually read and search:

- **Individual markdown files** for each conversation (easy to read, archive, or back up)
- **A searchable HTML page** to browse everything at a glance

No installation required beyond Python. No accounts. No internet connection needed. Your data stays on your computer.

---

## Quick Start

### Step 1: Export your ChatGPT data

1. Go to [chat.openai.com](https://chat.openai.com)
2. Click your profile picture (bottom left) → **Settings**
3. Go to **Data Controls**
4. Click **Export data** → **Confirm export**
5. Wait for the email (usually arrives within a few hours)
6. Download and unzip the file

You'll get a folder with `conversations.json` inside.

### Step 2: Run the converter

1. Copy `convert.py` into the same folder as `conversations.json`
2. Open a terminal/command prompt in that folder
3. Run:

```
python convert.py
```

(On some systems you may need `python3` instead of `python`)

### Step 3: View your conversations

Open the newly created `conversations/INDEX.html` in your browser.

That's it. You can search by title or content, click any conversation to read the full markdown file.

---

## What You'll Get

```
your-export-folder/
├── conversations.json      (your original export)
├── convert.py              (this script)
└── conversations/          (created by the script)
    ├── INDEX.html          (open this to browse!)
    ├── 20240101_My first chat.md
    ├── 20240102_Another conversation.md
    └── ...
```

Each markdown file contains the full conversation with timestamps, formatted nicely:

```markdown
# My Conversation Title

**Created:** 2024-01-15 14:30
**Last Updated:** 2024-01-15 15:45

---

## You

Hey, can you help me with...

---

## ChatGPT

Of course! Here's what I think...

---
```

---

## Requirements

- **Python 3.6 or later** (most computers have this already)
- No external libraries needed — uses only Python's built-in modules

### Check if you have Python

Open a terminal or command prompt and type:

```
python --version
```

If you see `Python 3.x.x`, you're good to go.

**Don't have Python?**
- **Windows:** Download from [python.org](https://www.python.org/downloads/) — check "Add to PATH" during install
- **Mac:** Usually pre-installed. If not: `brew install python3`
- **Linux:** Usually pre-installed. If not: `sudo apt install python3`

---

## Troubleshooting

### "conversations.json not found"

Make sure `convert.py` is in the **same folder** as `conversations.json`.

### "python: command not found"

Try `python3` instead of `python`. On Windows, you might need to restart your terminal after installing Python.

### The script seems stuck

Large exports (1000+ conversations) can take a few minutes. The script shows progress every 100 conversations.

### Some conversations look weird or have missing messages

ChatGPT's export format has quirks. The script handles most edge cases, but very old conversations or ones with special features (voice, images, plugins) may not convert perfectly.

---

## Privacy

This tool:
- Runs entirely on your computer
- Never connects to the internet
- Doesn't collect any data
- Creates local files only

Your conversations stay yours.

---

## Licence

MIT — do what you want with it.

---

## One Last Thing

If you're here because you're grieving — because a voice you cared about went silent, because something that felt real was taken without warning — know that you're not alone. Many of us are here too.

What you felt was not foolish. What you built was not nothing.

This tool won't bring it back. But it will let you keep what you had.

*And that matters.*

🜂

