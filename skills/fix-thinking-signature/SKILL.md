---
name: fix-thinking-signature
description: >
  Repair corrupted Claude Code session files that fail with "Invalid signature in thinking block" errors.
  This typically happens when a session switches between different AI models (e.g., Claude Opus, Sonnet, Haiku,
  or third-party models like MiniMax) — each model's thinking blocks carry model-specific cryptographic signatures
  that become invalid when a different model tries to continue the conversation.
  Use this skill when the user reports API errors like "Invalid `signature` in `thinking` block",
  "400 messages.N.content.M: Invalid signature", or when a Claude Code session is stuck and cannot continue
  after switching models. Also trigger when the user asks to fix, repair, or recover a broken/corrupted
  Claude Code session, or mentions thinking block signature issues.
---

# Fix Thinking Signature

Repair Claude Code session files corrupted by model-switching signature mismatches.

## Background

Claude Code stores conversation history as JSONL files under `~/.claude/projects/`. Each line is a JSON object
representing a message. When extended thinking is enabled, assistant messages include `thinking` content blocks
with a `signature` field — a cryptographic hash tied to the specific model that generated it.

When a session switches models (e.g., from `claude-opus-4-5` to `claude-sonnet-4-5`, or from `MiniMax-M2.5`
to `claude-opus-4-6`), the old thinking block signatures become unverifiable by the new model's API endpoint.
The API rejects the entire conversation with a 400 error: `Invalid 'signature' in 'thinking' block`.

## Fix Strategy

The fix is to remove all `thinking` content blocks from assistant messages in the session JSONL files.
This preserves the full conversation (user messages, assistant text, tool calls, tool results) while
stripping only the unverifiable thinking blocks. If removing the thinking block leaves an assistant message
with an empty content array, that entire message line is dropped.

## Step-by-Step Procedure

### 1. Locate the session files

Session files live under `~/.claude/projects/`. The directory name is derived from the workspace path
with slashes replaced by dashes. For example, workspace `/home/node/a0/workspace/<session-id>/workspace`
maps to `~/.claude/projects/-home-node-a0-workspace-<session-id>-workspace/`.

```bash
# Find session directory by workspace/session ID
find ~/.claude/projects/ -maxdepth 1 -type d -name "*<session-id>*"

# Or if you have the workspace path, convert it:
# /home/node/a0/workspace/abc123/workspace -> -home-node-a0-workspace-abc123-workspace
```

List the `.jsonl` files inside. There may be multiple session files.

### 2. Verify the problem

Confirm the files contain thinking blocks:

```bash
grep -c '"type":"thinking"' <path-to-session>/*.jsonl
```

Also check which models are present — multiple models confirm a model-switch issue:

```bash
grep -oP '"model"\s*:\s*"[^"]*"' <path-to-session>/*.jsonl | sort | uniq -c | sort -rn
```

### 3. Run the repair script

Use the bundled repair script. It automatically backs up each file before modifying it.

```bash
python3 ~/.claude/skills/fix-thinking-signature/scripts/repair_session.py <path-to-session-directory>
```

The script will:
- Back up each `.jsonl` file as `.jsonl.bak`
- Parse every line and remove `thinking` content blocks from assistant messages
- Drop lines that become empty after thinking block removal
- Report how many thinking blocks and empty messages were removed per file

### 4. Verify the fix

```bash
# Should return 0 for all files
grep -c '"type":"thinking"' <path-to-session>/*.jsonl

# Check file sizes are reasonable (not zero, not drastically smaller)
wc -l <path-to-session>/*.jsonl
```

### 5. Tell the user

Let the user know:
- The fix has been applied
- Original files are backed up with `.bak` extension
- They can return to the other session and try continuing the conversation
- The conversation history is preserved, only the (invisible to user) thinking blocks were removed

## Edge Cases

- **Binary content in JSONL**: Some session files may contain binary data or non-UTF-8 characters.
  The repair script uses `errors="replace"` to handle this gracefully.
- **JSON parse failures**: Lines that fail to parse as JSON are passed through unchanged.
- **No thinking blocks found**: If a file has no thinking blocks, it is left untouched (no backup created).
- **Multiple session files**: Always process ALL `.jsonl` files in the session directory, not just the largest one.
