"""Split an .mbox export (e.g. Gmail Takeout) into one .eml file per message.

Usage:
    python tools/mbox_to_eml.py path/to/export.mbox samples/legit
    python tools/mbox_to_eml.py path/to/export.mbox samples/legit --dry-run

- Existing files in the output folder are never overwritten; new files are named
  mbox-0001.eml, mbox-0002.eml, ... skipping any name that is already taken.
- A message is skipped if its Message-ID is already in the output folder (or earlier
  in the same mbox). Messages without a Message-ID are de-duplicated by content hash.
- Messages are written byte-for-byte as stored in the mbox, so headers are untouched.
"""
import argparse
import hashlib
import mailbox
from email import message_from_bytes, policy
from pathlib import Path


def message_id(raw):
    """Normalized Message-ID of a raw message, or '' if it has none."""
    msg = message_from_bytes(raw, policy=policy.compat32)
    return str(msg.get("Message-ID") or "").strip().strip("<>").strip().lower()


def content_hash(raw):
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def existing_keys(folder):
    """Message-IDs and content hashes of every .eml already in the folder."""
    ids, hashes = set(), set()
    for path in folder.glob("*.eml"):
        raw = path.read_bytes()
        mid = message_id(raw)
        if mid:
            ids.add(mid)
        hashes.add(content_hash(raw))
    return ids, hashes


def next_free_name(folder, counter):
    while True:
        counter += 1
        path = folder / f"mbox-{counter:04d}.eml"
        if not path.exists():
            return path, counter


def split(mbox_path, out_dir, dry_run=False):
    out_dir.mkdir(parents=True, exist_ok=True)
    ids, hashes = existing_keys(out_dir)
    stats = {"read": 0, "written": 0, "dup_message_id": 0, "dup_content": 0}
    counter = 0

    box = mailbox.mbox(str(mbox_path), create=False)
    try:
        for key in box.iterkeys():
            raw = box.get_bytes(key)
            stats["read"] += 1
            mid, digest = message_id(raw), content_hash(raw)
            if mid and mid in ids:
                stats["dup_message_id"] += 1
                continue
            if not mid and digest in hashes:
                stats["dup_content"] += 1
                continue
            path, counter = next_free_name(out_dir, counter)
            if not dry_run:
                path.write_bytes(raw)
            if mid:
                ids.add(mid)
            hashes.add(digest)
            stats["written"] += 1
    finally:
        box.close()
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mbox", type=Path, help="the .mbox file to split")
    parser.add_argument("out_dir", type=Path, help="folder to write .eml files into")
    parser.add_argument("--dry-run", action="store_true", help="count only, write nothing")
    args = parser.parse_args()

    stats = split(args.mbox, args.out_dir, args.dry_run)
    verb = "Would write" if args.dry_run else "Wrote"
    print(f"Read {stats['read']} messages from {args.mbox.name}")
    print(f"{verb} {stats['written']} new .eml files to {args.out_dir}")
    print(f"Skipped {stats['dup_message_id']} duplicate Message-IDs, "
          f"{stats['dup_content']} duplicate messages without a Message-ID")


if __name__ == "__main__":
    main()
