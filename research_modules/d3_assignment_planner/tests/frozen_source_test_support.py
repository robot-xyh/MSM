from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import subprocess
from typing import Sequence


def frozen_git_source_tree_sha256(
    repository_root: Path,
    *,
    module_path: str,
    commit: str,
    relative_files: Sequence[str],
) -> str:
    """Hash immutable source bytes from the commit bound to old evidence."""

    digest = sha256()
    for relative in sorted(str(value) for value in relative_files):
        completed = subprocess.run(
            ["git", "show", f"{commit}:{module_path}/{relative}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        )
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256(completed.stdout).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
