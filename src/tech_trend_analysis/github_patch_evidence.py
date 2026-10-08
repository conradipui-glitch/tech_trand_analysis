"""Extract bounded, immutable same-commit source-line evidence.

Only added, non-comment executable source lines can support implementation.
Never treat current README, a filename alone, removed lines, or tests/examples
as source-code implementation proof. Source diffs are still untrusted text;
the rule gate must check technology identity/context independently.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

_SOURCE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".cpp", ".cc", ".c", ".h", ".go", ".java", ".cs")
_NOT_SOURCE = re.compile(r"(?i)(?:^|/)(?:docs?|tests?|test|examples?|tutorials?|notebooks?|fixtures?|vendor|node_modules|generated)/|(?:^|/)test_[^/]+$|(?:^|/)[^/]+(?:_test|\.test|\.spec)\.[a-z]+$")
_RELEVANCE = re.compile(
    r"(?i)(?:lora|low.rank|peft|adapter|train|finetun|retriev|rag|vector|embed|generat|query|knowledge|model|tokeniz)"
)


def extract_source_patch(files: Sequence[dict[str, Any]], *, max_files: int = 8, max_lines: int = 14) -> str | None:
    """Return bounded evidence with FILE markers; no evidence => None.

    The original path and code lines come exclusively from GitHub's commit
    files[] API for the specific commit SHA supplied by the history client.
    """
    chunks: list[str] = []
    for f in files[:60]:
        if not isinstance(f, dict):
            continue
        path = str(f.get("filename") or "").replace("\\", "/")
        if not path.lower().endswith(_SOURCE_SUFFIXES) or _NOT_SOURCE.search(path):
            continue
        patch = f.get("patch")
        if not isinstance(patch, str):
            continue
        added: list[str] = []
        for line in patch.splitlines():
            if not line.startswith("+") or line.startswith("+++"):
                continue
            code = line[1:].strip()
            if (not code or code.startswith(("#", "//", "/*", "*", "--"))
                    or not _RELEVANCE.search(code)):
                continue
            added.append(code[:220])
            if len(added) >= max_lines:
                break
        if added:
            chunks.append("FILE " + path + "\n" + "\n".join("+" + line for line in added))
        if len(chunks) >= max_files:
            break
    return "\n".join(chunks)[:4500] if chunks else None
