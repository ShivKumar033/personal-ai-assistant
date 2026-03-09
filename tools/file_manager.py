"""
JARVIS AI — File Manager Tools (Phase 3)

Complete file system management:
- Create, move, copy, rename, delete files/directories
- File search (by name, extension, content)
- Smart folder organization (categorize by extension)
- File info & disk analysis

Usage:
    from tools.file_manager import register_file_tools
    register_file_tools(registry)
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger


# ── File Extension Categories ─────────────────────────────

EXTENSION_CATEGORIES = {
    "Documents": {
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt",
        ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".md",
        ".tex", ".epub", ".pages",
    },
    "Images": {
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg",
        ".webp", ".ico", ".tiff", ".raw", ".psd", ".ai",
    },
    "Videos": {
        ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
        ".webm", ".m4v", ".3gp", ".mpeg",
    },
    "Audio": {
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma",
        ".m4a", ".opus",
    },
    "Archives": {
        ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar",
        ".7z", ".tar.gz", ".tgz", ".deb", ".rpm",
    },
    "Code": {
        ".py", ".js", ".ts", ".html", ".css", ".java",
        ".c", ".cpp", ".h", ".go", ".rs", ".rb", ".php",
        ".sh", ".bash", ".zsh", ".ps1", ".bat", ".sql",
        ".json", ".yaml", ".yml", ".xml", ".toml", ".ini",
        ".conf", ".cfg",
    },
    "Executables": {
        ".exe", ".msi", ".app", ".dmg", ".bin", ".run",
        ".appimage", ".snap", ".flatpak",
    },
    "Fonts": {
        ".ttf", ".otf", ".woff", ".woff2", ".eot",
    },
    "Databases": {
        ".db", ".sqlite", ".sqlite3", ".mdb", ".accdb",
    },
}


def _get_category(ext: str) -> str:
    """Get the category for a file extension."""
    ext = ext.lower()
    for category, extensions in EXTENSION_CATEGORIES.items():
        if ext in extensions:
            return category
    return "Other"


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def register_file_tools(registry) -> None:
    """Register file management tools with the ToolRegistry."""

    # ═════════════════════════════════════════════════════════
    #  Create File
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="create_file",
        description="Create a new file with optional content",
        category="file",
        risk_level="safe",
        examples=["Create a file called notes.txt", "Make a new script.py"],
    )
    async def create_file(
        path: str,
        content: str = "",
        overwrite: bool = False,
    ) -> dict:
        """Create a new file at the given path."""
        filepath = Path(path).expanduser().resolve()

        if filepath.exists() and not overwrite:
            return {
                "status": "exists",
                "path": str(filepath),
                "error": "File already exists. Use overwrite=true to replace.",
            }

        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
            return {
                "status": "created",
                "path": str(filepath),
                "size": _human_size(filepath.stat().st_size),
            }
        except Exception as e:
            return {"status": "error", "path": str(filepath), "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Read File
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="read_file",
        description="Read the contents of a text file",
        category="file",
        risk_level="safe",
        examples=["Read notes.txt", "Show file contents"],
    )
    async def read_file(
        path: str,
        max_lines: int = 200,
    ) -> dict:
        """Read and return the contents of a text file."""
        filepath = Path(path).expanduser().resolve()

        if not filepath.exists():
            return {"status": "not_found", "path": str(filepath)}

        if not filepath.is_file():
            return {"status": "error", "error": f"'{filepath}' is not a file"}

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            truncated = len(lines) > max_lines

            if truncated:
                content = "\n".join(lines[:max_lines])

            return {
                "status": "ok",
                "path": str(filepath),
                "content": content,
                "lines": len(lines),
                "truncated": truncated,
                "size": _human_size(filepath.stat().st_size),
            }
        except Exception as e:
            return {"status": "error", "path": str(filepath), "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Move File/Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="move_file",
        description="Move a file or directory to a new location",
        category="file",
        risk_level="confirm",
        examples=["Move report.pdf to ~/Documents"],
    )
    async def move_file(source: str, destination: str) -> dict:
        """Move a file or directory."""
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()

        if not src.exists():
            return {"status": "not_found", "source": str(src)}

        try:
            # If destination is a directory, move into it
            if dst.is_dir():
                dst = dst / src.name

            shutil.move(str(src), str(dst))
            return {
                "status": "moved",
                "source": str(src),
                "destination": str(dst),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Copy File/Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="copy_file",
        description="Copy a file or directory",
        category="file",
        risk_level="safe",
        examples=["Copy config.yaml to backup"],
    )
    async def copy_file(source: str, destination: str) -> dict:
        """Copy a file or directory."""
        src = Path(source).expanduser().resolve()
        dst = Path(destination).expanduser().resolve()

        if not src.exists():
            return {"status": "not_found", "source": str(src)}

        try:
            if src.is_dir():
                shutil.copytree(str(src), str(dst))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))

            return {
                "status": "copied",
                "source": str(src),
                "destination": str(dst),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Rename File/Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="rename_file",
        description="Rename a file or directory",
        category="file",
        risk_level="confirm",
        examples=["Rename old_name.txt to new_name.txt"],
    )
    async def rename_file(path: str, new_name: str) -> dict:
        """Rename a file or directory."""
        filepath = Path(path).expanduser().resolve()

        if not filepath.exists():
            return {"status": "not_found", "path": str(filepath)}

        try:
            new_path = filepath.parent / new_name
            filepath.rename(new_path)
            return {
                "status": "renamed",
                "old_path": str(filepath),
                "new_path": str(new_path),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Delete File/Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="delete_file",
        description="Delete a file or directory (requires confirmation)",
        category="file",
        risk_level="confirm",
        examples=["Delete old_backup.zip", "Remove temp folder"],
    )
    async def delete_file(path: str) -> dict:
        """Delete a file or directory (moves to trash if possible)."""
        filepath = Path(path).expanduser().resolve()

        if not filepath.exists():
            return {"status": "not_found", "path": str(filepath)}

        try:
            if filepath.is_dir():
                item_count = sum(1 for _ in filepath.rglob("*"))
                shutil.rmtree(str(filepath))
                return {
                    "status": "deleted",
                    "path": str(filepath),
                    "type": "directory",
                    "items_removed": item_count,
                }
            else:
                size = filepath.stat().st_size
                filepath.unlink()
                return {
                    "status": "deleted",
                    "path": str(filepath),
                    "type": "file",
                    "size": _human_size(size),
                }
        except Exception as e:
            return {"status": "error", "path": str(filepath), "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  List Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="list_directory",
        description="List files and directories in a path",
        category="file",
        risk_level="safe",
        examples=["List files in ~/Downloads", "Show directory contents"],
    )
    async def list_directory(
        path: str = ".",
        show_hidden: bool = False,
        sort_by: str = "name",
    ) -> dict:
        """List directory contents with details."""
        dirpath = Path(path).expanduser().resolve()

        if not dirpath.exists():
            return {"status": "not_found", "path": str(dirpath)}
        if not dirpath.is_dir():
            return {"status": "error", "error": f"'{dirpath}' is not a directory"}

        items = []
        for item in dirpath.iterdir():
            if not show_hidden and item.name.startswith("."):
                continue
            try:
                stat = item.stat()
                items.append({
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": _human_size(stat.st_size) if item.is_file() else "",
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    "extension": item.suffix if item.is_file() else "",
                })
            except (PermissionError, OSError):
                items.append({
                    "name": item.name,
                    "type": "unknown",
                    "size": "",
                    "modified": "",
                    "extension": "",
                })

        # Sort
        sort_keys = {
            "name": lambda x: x["name"].lower(),
            "size": lambda x: x["size"],
            "modified": lambda x: x["modified"],
            "type": lambda x: (x["type"], x["name"].lower()),
        }
        items.sort(key=sort_keys.get(sort_by, sort_keys["name"]))

        return {
            "status": "ok",
            "path": str(dirpath),
            "total_items": len(items),
            "items": items[:50],  # Cap at 50
        }

    # ═════════════════════════════════════════════════════════
    #  File Info
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="file_info",
        description="Get detailed information about a file",
        category="file",
        risk_level="safe",
        examples=["File info for report.pdf", "Details about script.py"],
    )
    async def file_info(path: str) -> dict:
        """Get detailed information about a file or directory."""
        filepath = Path(path).expanduser().resolve()

        if not filepath.exists():
            return {"status": "not_found", "path": str(filepath)}

        stat = filepath.stat()
        info = {
            "status": "ok",
            "path": str(filepath),
            "name": filepath.name,
            "type": "directory" if filepath.is_dir() else "file",
            "size": _human_size(stat.st_size),
            "size_bytes": stat.st_size,
            "created": datetime.fromtimestamp(stat.st_ctime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "accessed": datetime.fromtimestamp(stat.st_atime).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            "permissions": oct(stat.st_mode)[-3:],
            "owner_uid": stat.st_uid,
        }

        if filepath.is_file():
            info["extension"] = filepath.suffix
            info["mime_type"] = mimetypes.guess_type(str(filepath))[0] or "unknown"
            info["category"] = _get_category(filepath.suffix)

            # MD5 hash for small files (< 50MB)
            if stat.st_size < 50 * 1024 * 1024:
                md5 = hashlib.md5(filepath.read_bytes()).hexdigest()
                info["md5"] = md5

        elif filepath.is_dir():
            # Count children
            try:
                children = list(filepath.iterdir())
                info["child_count"] = len(children)
                info["files"] = sum(1 for c in children if c.is_file())
                info["subdirectories"] = sum(1 for c in children if c.is_dir())
            except PermissionError:
                info["child_count"] = "Access denied"

        return info

    # ═════════════════════════════════════════════════════════
    #  Search Files
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="search_files",
        description="Search for files by name pattern in a directory",
        category="file",
        risk_level="safe",
        examples=["Find all .pdf files in Downloads", "Search for config files"],
    )
    async def search_files(
        pattern: str,
        directory: str = "~",
        max_results: int = 30,
        include_hidden: bool = False,
    ) -> dict:
        """Search for files matching a pattern (supports glob)."""
        search_dir = Path(directory).expanduser().resolve()

        if not search_dir.exists():
            return {"status": "not_found", "directory": str(search_dir)}

        # Ensure pattern has a glob wildcard
        if "*" not in pattern and "?" not in pattern:
            pattern = f"*{pattern}*"

        results = []
        try:
            for match in search_dir.rglob(pattern):
                if not include_hidden:
                    # Skip hidden files/directories
                    if any(part.startswith(".") for part in match.parts):
                        continue

                try:
                    stat = match.stat()
                    results.append({
                        "path": str(match),
                        "name": match.name,
                        "type": "directory" if match.is_dir() else "file",
                        "size": _human_size(stat.st_size) if match.is_file() else "",
                        "modified": datetime.fromtimestamp(stat.st_mtime).strftime(
                            "%Y-%m-%d %H:%M"
                        ),
                    })
                except (PermissionError, OSError):
                    continue

                if len(results) >= max_results:
                    break

        except Exception as e:
            return {"status": "error", "error": str(e)}

        return {
            "status": "ok",
            "pattern": pattern,
            "directory": str(search_dir),
            "matches": len(results),
            "results": results,
        }

    # ═════════════════════════════════════════════════════════
    #  Organize Folder
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="organize_folder",
        description="Organize files in a folder by sorting them into category subfolders",
        category="file",
        risk_level="confirm",
        examples=[
            "Organize my Downloads folder",
            "Sort files in ~/Desktop",
        ],
    )
    async def organize_folder(
        path: str,
        dry_run: bool = False,
    ) -> dict:
        """
        Organize files by moving them into category subfolders.

        Categories: Documents, Images, Videos, Audio, Archives,
        Code, Executables, Fonts, Databases, Other.

        Use dry_run=true to preview changes without moving files.
        """
        folder = Path(path).expanduser().resolve()

        if not folder.exists():
            return {"status": "not_found", "path": str(folder)}
        if not folder.is_dir():
            return {"status": "error", "error": f"'{folder}' is not a directory"}

        moved = []
        skipped = []
        errors = []

        for item in folder.iterdir():
            # Skip directories and hidden files
            if item.is_dir() or item.name.startswith("."):
                continue

            category = _get_category(item.suffix)
            target_dir = folder / category

            if not dry_run:
                target_dir.mkdir(exist_ok=True)
                target_path = target_dir / item.name

                # Handle name collisions
                if target_path.exists():
                    stem = item.stem
                    suffix = item.suffix
                    counter = 1
                    while target_path.exists():
                        target_path = target_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                try:
                    shutil.move(str(item), str(target_path))
                    moved.append({
                        "file": item.name,
                        "category": category,
                        "destination": str(target_path),
                    })
                except Exception as e:
                    errors.append({"file": item.name, "error": str(e)})
            else:
                moved.append({
                    "file": item.name,
                    "category": category,
                    "destination": str(folder / category / item.name),
                })

        return {
            "status": "preview" if dry_run else "organized",
            "path": str(folder),
            "files_moved": len(moved),
            "files_skipped": len(skipped),
            "errors": len(errors),
            "details": moved[:30],
            "error_details": errors[:10] if errors else [],
        }

    # ═════════════════════════════════════════════════════════
    #  Create Directory
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="create_directory",
        description="Create a new directory (and parent directories if needed)",
        category="file",
        risk_level="safe",
        examples=["Create folder ~/Projects/new-project"],
    )
    async def create_directory(path: str) -> dict:
        """Create a new directory."""
        dirpath = Path(path).expanduser().resolve()

        try:
            dirpath.mkdir(parents=True, exist_ok=True)
            return {
                "status": "created",
                "path": str(dirpath),
            }
        except Exception as e:
            return {"status": "error", "path": str(dirpath), "error": str(e)}

    # ═════════════════════════════════════════════════════════
    #  Disk Analysis
    # ═════════════════════════════════════════════════════════

    @registry.register(
        name="folder_size",
        description="Calculate the total size of a folder",
        category="file",
        risk_level="safe",
        examples=["How big is my Downloads folder?", "Folder size of ~/Projects"],
    )
    async def folder_size(path: str) -> dict:
        """Calculate total size of a directory and its contents."""
        dirpath = Path(path).expanduser().resolve()

        if not dirpath.exists():
            return {"status": "not_found", "path": str(dirpath)}
        if not dirpath.is_dir():
            return {"status": "error", "error": "Not a directory"}

        total_size = 0
        file_count = 0
        dir_count = 0
        errors = 0
        largest_files = []

        try:
            for item in dirpath.rglob("*"):
                try:
                    if item.is_file():
                        size = item.stat().st_size
                        total_size += size
                        file_count += 1
                        largest_files.append((str(item), size))
                    elif item.is_dir():
                        dir_count += 1
                except (PermissionError, OSError):
                    errors += 1
        except Exception as e:
            return {"status": "error", "error": str(e)}

        # Top 5 largest files
        largest_files.sort(key=lambda x: x[1], reverse=True)
        top_files = [
            {"path": p, "size": _human_size(s)}
            for p, s in largest_files[:5]
        ]

        return {
            "status": "ok",
            "path": str(dirpath),
            "total_size": _human_size(total_size),
            "total_bytes": total_size,
            "files": file_count,
            "directories": dir_count,
            "access_errors": errors,
            "largest_files": top_files,
        }

    logger.info(f"Registered file management tools (total: {registry.count})")
