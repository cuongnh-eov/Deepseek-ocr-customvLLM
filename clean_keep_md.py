#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Giữ lại các file .md trong target nếu (stem của file .md) trùng với (stem của file .txt)
được liệt kê trong manifest.txt. Còn lại xóa hết.

Ví dụ:
  manifest.txt có: out1.txt  -> giữ out1.md
  manifest.txt có: abc.txt   -> giữ abc.md

Chạy thử (không xóa):
  python3 clean_keep_md.py --manifest ".../manifest.txt" --target ".../vn_handwritten_images" --dry-run

Chạy thật (xóa):
  python3 clean_keep_md.py --manifest ".../manifest.txt" --target ".../vn_handwritten_images" --apply --remove-empty-dirs
"""

from pathlib import Path
import argparse


def load_keep_stems(manifest_path: Path) -> set[str]:
    keep = set()
    text = manifest_path.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # manifest có thể chứa "out1.txt" hoặc "/a/b/out1.txt" -> lấy basename rồi stem
        name = Path(line).name
        keep.add(Path(name).stem)  # out1.txt -> out1
    return keep


def remove_empty_dirs(root: Path, dry_run: bool):
    # xóa thư mục rỗng từ dưới lên
    dirs = [p for p in root.rglob("*") if p.is_dir()]
    dirs.sort(key=lambda x: len(x.parts), reverse=True)
    for d in dirs:
        try:
            next(d.iterdir())
        except StopIteration:
            if dry_run:
                print(f"[DRY] rmdir {d}")
            else:
                try:
                    d.rmdir()
                except Exception as e:
                    print(f"[WARN] cannot rmdir {d}: {e}")


def main():
    ap = argparse.ArgumentParser(
        description="Keep only .md files whose stem matches stems from manifest(.txt). Delete everything else."
    )
    ap.add_argument("--manifest", required=True, help="Path to manifest.txt (each line: a txt filename)")
    ap.add_argument("--target", required=True, help="Target folder to clean")
    ap.add_argument("--dry-run", action="store_true", help="Print what would be deleted (default if not --apply)")
    ap.add_argument("--apply", action="store_true", help="Actually delete files")
    ap.add_argument("--remove-empty-dirs", action="store_true", help="Remove empty directories after deletion")
    args = ap.parse_args()

    manifest = Path(args.manifest)
    target = Path(args.target)

    if not manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest}")
    if not target.exists():
        raise FileNotFoundError(f"Target not found: {target}")

    keep_stems = load_keep_stems(manifest)
    if not keep_stems:
        raise ValueError("Manifest is empty or no valid filenames found.")

    dry_run = (not args.apply) or args.dry_run  # chỉ xóa khi có --apply

    kept = 0
    deleted = 0

    for p in target.rglob("*"):
        if not p.is_file():
            continue

        # GIỮ LẠI: <stem>.md nếu stem nằm trong keep_stems
        if p.suffix.lower() == ".md" and p.stem in keep_stems:
            kept += 1
            continue

        # CÒN LẠI: xóa
        if dry_run:
            print(f"[DRY] delete {p}")
        else:
            try:
                p.unlink()
            except Exception as e:
                print(f"[WARN] cannot delete {p}: {e}")
        deleted += 1

    if args.remove_empty_dirs:
        remove_empty_dirs(target, dry_run=dry_run)

    mode = "DRY-RUN" if dry_run else "APPLY"
    print(f"\n=== {mode} SUMMARY ===")
    print(f"Keep stems from manifest: {len(keep_stems)}")
    print(f"Kept .md: {kept}")
    print(f"Deleted files: {deleted}")


if __name__ == "__main__":
    main()
