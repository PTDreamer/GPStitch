"""File browser API endpoint for local mode."""

import logging
import os
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from gpstitch.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Allowed file extensions for the browser
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".gpx", ".fit", ".srt"}


class BrowseEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    extension: Optional[str] = None


class BrowseResponse(BaseModel):
    current_path: str
    parent_path: Optional[str] = None
    entries: List[BrowseEntry]


@router.get("/browse", response_model=BrowseResponse)
async def browse_files(
    path: Optional[str] = Query(None, description="Directory path to browse"),
    show_hidden: bool = Query(False, description="Show hidden files"),
) -> BrowseResponse:
    """Browse local filesystem directories.

    Returns a list of directories and allowed files in the specified path.
    """
    if not settings.local_mode:
        raise HTTPException(
            status_code=403,
            detail="Local file mode is disabled.",
        )

    # Default to /work if it exists (Docker environment), otherwise home directory
    if path is None or path.strip() == "":
        work_path = Path("/work")
        current = work_path if work_path.is_dir() else Path.home()
    else:
        current = Path(path).expanduser().resolve()

    if not current.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {current}")

    if not current.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {current}")

    parent = str(current.parent) if current != current.parent else None

    entries: List[BrowseEntry] = []

    try:
        for item in sorted(current.iterdir()):
            name = item.name

            # Skip hidden files unless requested
            if not show_hidden and name.startswith(".") and name != "..":
                continue

            is_dir = item.is_dir()
            ext = item.suffix.lower() if item.is_file() else None

            # Only show directories and allowed file types
            if is_dir or ext in ALLOWED_EXTENSIONS:
                entry = BrowseEntry(
                    name=name,
                    path=str(item),
                    is_dir=is_dir,
                    size=item.stat().st_size if item.is_file() else None,
                    extension=ext,
                )
                entries.append(entry)
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {current}")

    return BrowseResponse(
        current_path=str(current),
        parent_path=parent,
        entries=entries,
    )


@router.get("/browse/drives", response_model=List[str])
async def list_drives():
    """List available drives on Windows, or root on Unix."""
    if not settings.local_mode:
        raise HTTPException(
            status_code=403,
            detail="Local file mode is disabled.",
        )

    if os.name == "nt":
        # Windows: list available drives
        import string
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
        return drives
    else:
        return ["/"]
