#!/usr/bin/env python3
"""
Repair Claude Code session JSONL files by removing thinking blocks
with invalid signatures caused by model switching.

Usage:
    python3 repair_session.py <session-directory>
    python3 repair_session.py <path-to-specific-file.jsonl>

The script backs up each file as .jsonl.bak before modifying it.
Files with no thinking blocks are left untouched.
"""

import json
import os
import sys
import glob
import shutil


def repair_jsonl_file(filepath):
    """Remove thinking blocks from a single JSONL session file.

    Returns a dict with stats about what was changed.
    """
    stats = {
        "file": filepath,
        "total_lines": 0,
        "thinking_blocks_removed": 0,
        "empty_messages_removed": 0,
        "output_lines": 0,
        "skipped": False,
    }

    # First pass: check if there are any thinking blocks at all
    has_thinking = False
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if '"type":"thinking"' in line or '"type": "thinking"' in line:
                    has_thinking = True
                    break
    except Exception as e:
        print(f"  ERROR reading {filepath}: {e}")
        stats["skipped"] = True
        return stats

    if not has_thinking:
        print(f"  No thinking blocks found in {os.path.basename(filepath)} - skipping")
        stats["skipped"] = True
        return stats

    # Create backup
    backup_path = filepath + ".bak"
    if os.path.exists(backup_path):
        print(f"  Backup already exists: {os.path.basename(backup_path)}")
    else:
        shutil.copy2(filepath, backup_path)
        print(f"  Backed up to {os.path.basename(backup_path)}")

    # Second pass: read from backup, write repaired version
    fixed_lines = []
    with open(backup_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stats["total_lines"] += 1
            stripped = line.strip()

            if not stripped:
                fixed_lines.append("")
                continue

            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                # Keep unparseable lines as-is
                fixed_lines.append(stripped)
                continue

            msg = obj.get("message", {})
            content = msg.get("content", [])

            if isinstance(content, list):
                new_content = []
                had_thinking = False

                for block in content:
                    if isinstance(block, dict) and block.get("type") == "thinking":
                        had_thinking = True
                        stats["thinking_blocks_removed"] += 1
                    else:
                        new_content.append(block)

                if had_thinking:
                    if len(new_content) == 0:
                        # Entire message was just thinking - drop the line
                        stats["empty_messages_removed"] += 1
                        continue
                    else:
                        msg["content"] = new_content
                        obj["message"] = msg

            fixed_lines.append(json.dumps(obj, ensure_ascii=False))

    # Write repaired file
    with open(filepath, "w", encoding="utf-8") as f:
        for line in fixed_lines:
            f.write(line + "\n")

    stats["output_lines"] = len(fixed_lines)
    return stats


def main():
    if len(sys.argv) < 2:
        print("Usage: repair_session.py <session-directory-or-file>")
        print()
        print("Examples:")
        print("  repair_session.py ~/.claude/projects/-home-node-a0-workspace-abc123-workspace/")
        print("  repair_session.py ./my-session.jsonl")
        sys.exit(1)

    target = sys.argv[1]

    # Collect JSONL files
    if os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, "*.jsonl")))
        # Exclude backup files
        files = [f for f in files if not f.endswith(".bak")]
        if not files:
            print(f"No .jsonl files found in {target}")
            sys.exit(1)
        print(f"Found {len(files)} session file(s) in {target}")
    elif os.path.isfile(target) and target.endswith(".jsonl"):
        files = [target]
    else:
        print(f"Error: {target} is not a directory or .jsonl file")
        sys.exit(1)

    print()
    total_thinking = 0
    total_empty = 0

    for filepath in files:
        print(f"Processing: {os.path.basename(filepath)}")
        stats = repair_jsonl_file(filepath)

        if not stats["skipped"]:
            total_thinking += stats["thinking_blocks_removed"]
            total_empty += stats["empty_messages_removed"]
            print(f"  Lines: {stats['total_lines']} -> {stats['output_lines']}")
            print(f"  Thinking blocks removed: {stats['thinking_blocks_removed']}")
            print(f"  Empty messages dropped: {stats['empty_messages_removed']}")
        print()

    print("=" * 50)
    print(f"Total thinking blocks removed: {total_thinking}")
    print(f"Total empty messages dropped: {total_empty}")

    if total_thinking > 0:
        print("\nRepair complete. Original files backed up with .bak extension.")
        print("You can now try resuming the session.")
    else:
        print("\nNo repairs needed - no thinking blocks found in any file.")


if __name__ == "__main__":
    main()
