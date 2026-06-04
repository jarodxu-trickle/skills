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

### Important: split-turn `message.id` collisions (the subtle case)

Simply deleting `thinking` lines is **not always enough**. A streamed assistant turn with extended thinking
is frequently logged as **multiple JSONL lines that share a single `message.id`** — e.g. one line carrying
the `thinking` block (with the bad signature) and a separate line carrying the `text` block. On resume,
the conversation is reconstructed by **grouping content blocks by `message.id`**.

If you delete only the `thinking` line, the surviving `text` line **keeps the same `message.id`**, which can
still be re-associated with the (cached/streamed) thinking content during reconstruction — so the
`Invalid signature in thinking block` error **persists even though the file appears to have no thinking blocks**.

The repair script therefore also:
1. **Regenerates the `message.id`** of any surviving message that shared an id with a removed thinking block,
   giving it a fresh unique id so it can never be re-grouped with the stripped thinking content.
2. **Relinks `parentUuid`** references: when a thinking-only line is dropped, its children would point to a
   now-missing uuid. The script walks up the parent chain and repoints orphaned children to the nearest
   surviving ancestor, keeping the conversation tree intact.

### CRITICAL: a live SDK subprocess holds the conversation in memory (the real root cause in happycapy)

Repairing the JSONL on disk is often **not sufficient on its own**. Hosts like happycapy run the
conversation through the **Claude Agent SDK in streaming-input mode** (`CLAUDE_CODE_ENTRYPOINT=sdk-ts`),
which spawns a **long-running `claude` subprocess per project**. That subprocess loads the whole
conversation into memory at startup and **stays alive across turns**. Every "continue"/"继续" is routed to
the same live subprocess, which rebuilds the API request from its **in-memory copy** — which still contains
the bad thinking block. As a result:

> **Editing the on-disk JSONL has no effect while that subprocess is alive.** Switching sessions in the UI
> is also not enough, because the host keeps the subprocess running.

The tell-tale sign: the JSONL is verifiably clean (`grep -c '"type":"thinking"'` returns 0, the active
`parentUuid` chain has no thinking blocks), yet a **fresh** `messages.N.content.M: Invalid signature` error
is still produced at the **identical index** after the repair.

**The fix that actually works:** after repairing the JSONL, **terminate the stale subprocess** so the host
respawns a fresh `resume` that re-reads the clean transcript from disk. See Step 4b below. No conversation
is lost — the on-disk JSONL is the complete source of truth that the fresh process reconstructs from.

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
- Regenerate the `message.id` of any surviving message that shared an id with a removed thinking block
  (defeats split-turn re-association — see Fix Strategy)
- Relink `parentUuid` references orphaned by dropped lines
- Report thinking blocks removed, empty messages dropped, ids regenerated, and parents relinked per file

### 4. Verify the fix

```bash
# Should return 0 for all files
grep -c '"type":"thinking"' <path-to-session>/*.jsonl

# Check file sizes are reasonable (not zero, not drastically smaller)
wc -l <path-to-session>/*.jsonl
```

### 4b. Restart the stale SDK subprocess (REQUIRED when the host keeps it alive)

If the error persists at the same `messages.N` index after a clean repair, the host is serving the
conversation from a long-running `claude` subprocess's memory. Terminate it so a fresh `resume` reads the
clean transcript.

```bash
# List every claude subprocess and the workspace it is bound to
for p in $(pgrep -x claude); do echo "$p $(readlink /proc/$p/cwd)"; done
```

Identify the PID(s) whose cwd is the **broken project's** workspace
(`/home/node/a0/workspace/<PROJECT-ID>/workspace`). There may be several lingering ones — kill them all:

```bash
BROKEN="/home/node/a0/workspace/<PROJECT-ID>/workspace"
for p in $(pgrep -x claude); do
  [ "$(readlink /proc/$p/cwd)" = "$BROKEN" ] && kill -TERM "$p"
done
```

**Safety — never kill the wrong process:**
- **Do NOT** kill the `claude` PID whose cwd is *your own* current workspace (that is the session running
  this skill — killing it terminates yourself).
- **Do NOT** kill the orchestrator `node dist/index.js` (the parent of all `claude` procs); it is shared by
  every session.
- Match strictly by cwd equal to the broken project's workspace path.

After the kill, the next "continue"/"继续" in the broken session causes the host to respawn `query()` with
`resume:<sessionId>`, which reads the repaired transcript. The error is then gone.

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
