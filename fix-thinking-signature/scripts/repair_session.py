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
import uuid


def repair_jsonl_file(filepath):
    """Remove thinking blocks from a single JSONL session file.

    Returns a dict with stats about what was changed.
    """
    stats = {
        "file": filepath,
        "total_lines": 0,
        "thinking_blocks_removed": 0,
        "empty_messages_removed": 0,
        "ids_regenerated": 0,
        "parents_relinked": 0,
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

    # Load all entries from backup
    raw_lines = []
    with open(backup_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stats["total_lines"] += 1
            raw_lines.append(line.rstrip("\n"))

    # Pass A: identify message.ids that contained a thinking block, and the
    # uuid->parentUuid map. A streamed assistant turn with extended thinking is
    # often logged as MULTIPLE JSONL lines that share one message.id (e.g. one
    # line with the thinking block, a separate line with the text). Removing only
    # the thinking line leaves a surviving line whose message.id still maps to the
    # (now-stripped) thinking content on resume/reconstruction, which re-triggers
    # the invalid-signature error. We track those ids so we can give survivors a
    # fresh, unique message.id and sever that association.
    thinking_msg_ids = set()
    uuid_to_parent = {}
    for stripped in raw_lines:
        s = stripped.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            continue
        if obj.get("uuid"):
            uuid_to_parent[obj["uuid"]] = obj.get("parentUuid")
        msg = obj.get("message", {}) or {}
        content = msg.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    if msg.get("id"):
                        thinking_msg_ids.add(msg["id"])

    # Pass B: rewrite. Remove thinking blocks; drop now-empty messages; record
    # the uuids of dropped lines so we can relink orphaned children.
    fixed_objs = []
    dropped_uuid_to_parent = {}  # uuid of dropped line -> its parentUuid

    for stripped in raw_lines:
        s = stripped.strip()

        if not s:
            fixed_objs.append(("")); continue

        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            fixed_objs.append((stripped)); continue

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
                    # Entire message was just thinking - drop the line and
                    # remember its parent so children can be relinked.
                    stats["empty_messages_removed"] += 1
                    if obj.get("uuid"):
                        dropped_uuid_to_parent[obj["uuid"]] = obj.get("parentUuid")
                    continue
                else:
                    msg["content"] = new_content
                    obj["message"] = msg

        fixed_objs.append(obj)

    # Pass C: for surviving messages whose message.id was associated with a
    # removed thinking block, assign a brand-new unique message.id. Also relink
    # any parentUuid that points to a dropped line, walking up until it lands on
    # a line that still exists.
    surviving_uuids = set()
    for obj in fixed_objs:
        if isinstance(obj, dict) and obj.get("uuid"):
            surviving_uuids.add(obj["uuid"])

    def resolve_parent(parent):
        # Walk up the dropped chain until we reach a surviving uuid (or None).
        seen = set()
        while parent in dropped_uuid_to_parent and parent not in seen:
            seen.add(parent)
            parent = dropped_uuid_to_parent[parent]
        return parent

    for obj in fixed_objs:
        if not isinstance(obj, dict):
            continue
        msg = obj.get("message", {}) or {}
        # Regenerate message.id of survivors that shared an id with a thinking block
        if msg.get("id") and msg["id"] in thinking_msg_ids:
            msg["id"] = uuid.uuid4().hex
            obj["message"] = msg
            stats["ids_regenerated"] += 1
        # Relink orphaned parentUuid references
        parent = obj.get("parentUuid")
        if parent is not None and parent not in surviving_uuids:
            new_parent = resolve_parent(parent)
            if new_parent != parent:
                obj["parentUuid"] = new_parent
                stats["parents_relinked"] += 1

    # Serialize and write repaired file
    out_lines = []
    for obj in fixed_objs:
        if isinstance(obj, dict):
            out_lines.append(json.dumps(obj, ensure_ascii=False))
        else:
            out_lines.append(obj)

    with open(filepath, "w", encoding="utf-8") as f:
        for line in out_lines:
            f.write(line + "\n")

    stats["output_lines"] = len(out_lines)
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
    total_ids = 0
    total_parents = 0

    for filepath in files:
        print(f"Processing: {os.path.basename(filepath)}")
        stats = repair_jsonl_file(filepath)

        if not stats["skipped"]:
            total_thinking += stats["thinking_blocks_removed"]
            total_empty += stats["empty_messages_removed"]
            total_ids += stats["ids_regenerated"]
            total_parents += stats["parents_relinked"]
            print(f"  Lines: {stats['total_lines']} -> {stats['output_lines']}")
            print(f"  Thinking blocks removed: {stats['thinking_blocks_removed']}")
            print(f"  Empty messages dropped: {stats['empty_messages_removed']}")
            print(f"  message.id regenerated (split-turn survivors): {stats['ids_regenerated']}")
            print(f"  parentUuid references relinked: {stats['parents_relinked']}")
        print()

    print("=" * 50)
    print(f"Total thinking blocks removed: {total_thinking}")
    print(f"Total empty messages dropped: {total_empty}")
    print(f"Total message.id regenerated: {total_ids}")
    print(f"Total parentUuid relinked: {total_parents}")

    if total_thinking > 0:
        print("\nRepair complete. Original files backed up with .bak extension.")
        print("You can now try resuming the session.")
    else:
        print("\nNo repairs needed - no thinking blocks found in any file.")


if __name__ == "__main__":
    main()
