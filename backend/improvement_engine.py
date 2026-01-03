"""
EHR Bridge - Self-Improving Feedback Loop Engine

This module implements the feedback loop that learns from observed traffic
and generates code improvements automatically.

FLOW:
    OBSERVE → ANALYZE → GENERATE → APPLY
       │                              │
       └──────── LEARN ───────────────┘

IMPROVEMENT TYPES:
1. new_endpoint - New API patterns discovered
2. schema_change - Response structure changes
3. parse_error - Parsing failures to fix
4. optimization - Performance improvements
"""

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum

# ============================================================
# CONFIGURATION
# ============================================================

IMPROVEMENT_CONFIG = {
    "auto_apply": False,           # Require manual review
    "min_confidence": 0.8,         # Only suggest high-confidence changes
    "max_pending": 20,             # Limit pending queue
    "notify_on_critical": True,    # Alert for critical fixes
    "allowed_file_types": [".py", ".js", ".ts", ".tsx"],
    "improvements_dir": ".improvements"
}

# ============================================================
# TYPES
# ============================================================

class ImprovementType(str, Enum):
    NEW_ENDPOINT = "new_endpoint"
    SCHEMA_CHANGE = "schema_change"
    PARSE_ERROR = "parse_error"
    OPTIMIZATION = "optimization"
    NEW_PARSER = "new_parser"
    BUG_FIX = "bug_fix"

class ImprovementStatus(str, Enum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"

class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class FileChange:
    file_path: str
    action: str  # "add", "modify", "delete"
    line_number: Optional[int]
    old_content: Optional[str]
    new_content: str
    description: str

@dataclass
class Improvement:
    id: str
    type: ImprovementType
    title: str
    description: str
    priority: Priority
    confidence: float
    agent: str  # "claude", "gemini", "codex"
    changes: List[FileChange]
    analysis: Dict[str, Any]
    created_at: str
    status: ImprovementStatus = ImprovementStatus.PENDING
    applied_at: Optional[str] = None
    rejected_reason: Optional[str] = None

# ============================================================
# ENGINE
# ============================================================

class ImprovementEngine:
    """
    Manages the self-improving feedback loop.

    Responsibilities:
    - Observe: Track errors, patterns, schema changes
    - Analyze: Identify improvement opportunities
    - Generate: Create code suggestions via Codex
    - Apply: Manage review and application workflow
    """

    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.improvements_dir = self.base_dir / IMPROVEMENT_CONFIG["improvements_dir"]
        self._ensure_directories()

    def _ensure_directories(self):
        """Create improvement directories if they don't exist."""
        for subdir in ["pending", "applied", "rejected"]:
            (self.improvements_dir / subdir).mkdir(parents=True, exist_ok=True)

    def _generate_id(self, content: str) -> str:
        """Generate a short unique ID for an improvement."""
        hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
        count = len(list((self.improvements_dir / "pending").glob("*.json"))) + 1
        return f"{count:03d}_{hash_val}"

    # ==================== OBSERVE ====================

    def observe_error(self, error: Exception, context: Dict[str, Any]) -> Optional[str]:
        """
        Observe a parsing or processing error.
        Returns improvement ID if one was generated.
        """
        error_info = {
            "type": type(error).__name__,
            "message": str(error),
            "file": context.get("file"),
            "line": context.get("line"),
            "function": context.get("function"),
            "input_sample": context.get("input_sample", {})
        }

        # Check if this is a known error pattern
        if isinstance(error, KeyError):
            return self._handle_missing_key_error(error_info, context)
        elif isinstance(error, TypeError):
            return self._handle_type_error(error_info, context)

        return None

    def observe_endpoint(self, request: Dict[str, Any], response: Dict[str, Any]) -> Optional[str]:
        """
        Observe a new endpoint pattern.
        Returns improvement ID if a new endpoint was discovered.
        """
        url = request.get("url", "")
        method = request.get("method", "GET")

        # Extract pattern (replace IDs with placeholders)
        pattern = self._extract_pattern(url)

        # Check if this pattern is already known
        if self._is_known_pattern(pattern):
            return None

        # Generate improvement for new endpoint
        improvement = Improvement(
            id=self._generate_id(pattern),
            type=ImprovementType.NEW_ENDPOINT,
            title=f"New Endpoint: {pattern}",
            description=f"Discovered new API endpoint pattern during observation.",
            priority=Priority.MEDIUM,
            confidence=0.9,
            agent="codex",
            changes=[],  # Will be populated by Codex
            analysis={
                "pattern": pattern,
                "method": method,
                "sample_url": url,
                "response_keys": list(response.keys()) if isinstance(response, dict) else [],
                "response_sample": self._truncate_sample(response)
            },
            created_at=datetime.now().isoformat()
        )

        return self._save_improvement(improvement)

    def observe_schema_change(self, endpoint: str, old_schema: Dict, new_schema: Dict) -> Optional[str]:
        """
        Observe a schema change in an API response.
        Returns improvement ID if changes were detected.
        """
        changes = self._diff_schemas(old_schema, new_schema)

        if not changes:
            return None

        improvement = Improvement(
            id=self._generate_id(endpoint + str(changes)),
            type=ImprovementType.SCHEMA_CHANGE,
            title=f"Schema Change: {endpoint}",
            description=f"Detected {len(changes)} field changes in API response.",
            priority=Priority.HIGH,
            confidence=0.95,
            agent="codex",
            changes=[],  # Will be populated by Codex
            analysis={
                "endpoint": endpoint,
                "field_changes": changes,
                "old_keys": list(old_schema.keys()),
                "new_keys": list(new_schema.keys())
            },
            created_at=datetime.now().isoformat()
        )

        return self._save_improvement(improvement)

    # ==================== ANALYZE ====================

    def _handle_missing_key_error(self, error_info: Dict, context: Dict) -> Optional[str]:
        """Analyze a KeyError and generate fix suggestion."""
        missing_key = str(error_info["message"]).strip("'\"")

        improvement = Improvement(
            id=self._generate_id(f"keyerror_{missing_key}"),
            type=ImprovementType.PARSE_ERROR,
            title=f"Fix Missing Key: {missing_key}",
            description=f"Parser failed due to missing key '{missing_key}'.",
            priority=Priority.HIGH,
            confidence=0.85,
            agent="codex",
            changes=[
                FileChange(
                    file_path=error_info.get("file", "unknown"),
                    action="modify",
                    line_number=error_info.get("line"),
                    old_content=None,
                    new_content=f"# Add null-safe access for '{missing_key}'",
                    description=f"Use .get('{missing_key}') instead of direct access"
                )
            ],
            analysis={
                "error_type": "KeyError",
                "missing_key": missing_key,
                "available_keys": list(context.get("input_sample", {}).keys()),
                "suggestion": f"Use .get('{missing_key}') or add key existence check"
            },
            created_at=datetime.now().isoformat()
        )

        return self._save_improvement(improvement)

    def _handle_type_error(self, error_info: Dict, context: Dict) -> Optional[str]:
        """Analyze a TypeError and generate fix suggestion."""
        improvement = Improvement(
            id=self._generate_id(f"typeerror_{error_info['message'][:20]}"),
            type=ImprovementType.PARSE_ERROR,
            title=f"Fix Type Error",
            description=f"Parser failed due to type mismatch.",
            priority=Priority.MEDIUM,
            confidence=0.75,
            agent="codex",
            changes=[],
            analysis={
                "error_type": "TypeError",
                "message": error_info["message"],
                "suggestion": "Add type checking before operation"
            },
            created_at=datetime.now().isoformat()
        )

        return self._save_improvement(improvement)

    def _extract_pattern(self, url: str) -> str:
        """Extract a reusable pattern from a URL."""
        import re
        # Replace numeric IDs with placeholders
        pattern = re.sub(r'/\d+/', '/{id}/', url)
        pattern = re.sub(r'/\d+$', '/{id}', pattern)
        # Remove query string
        pattern = pattern.split('?')[0]
        return pattern

    def _is_known_pattern(self, pattern: str) -> bool:
        """Check if an endpoint pattern is already known."""
        known_patterns_file = self.base_dir / "data" / "known_endpoints.json"
        if not known_patterns_file.exists():
            return False

        try:
            with open(known_patterns_file) as f:
                known = json.load(f)
                return pattern in known.get("patterns", [])
        except:
            return False

    def _diff_schemas(self, old: Dict, new: Dict) -> List[Dict]:
        """Find differences between two schemas."""
        changes = []

        # Find removed keys
        for key in old.keys():
            if key not in new:
                changes.append({"type": "removed", "key": key})

        # Find added keys
        for key in new.keys():
            if key not in old:
                changes.append({"type": "added", "key": key})

        # Find renamed keys (heuristic: similar values)
        for old_key in old.keys():
            if old_key not in new:
                for new_key in new.keys():
                    if new_key not in old and old[old_key] == new.get(new_key):
                        changes.append({
                            "type": "renamed",
                            "old_key": old_key,
                            "new_key": new_key
                        })

        return changes

    def _truncate_sample(self, data: Any, max_len: int = 500) -> Any:
        """Truncate sample data to reasonable size."""
        text = json.dumps(data) if not isinstance(data, str) else data
        if len(text) > max_len:
            return json.loads(text[:max_len] + "...truncated")
        return data

    # ==================== GENERATE ====================

    async def generate_code_fix(self, improvement: Improvement) -> Improvement:
        """
        Use Codex to generate actual code changes for an improvement.
        """
        from .ai_agents import delegate_to_codex, AgentTask

        task = AgentTask(
            agent="codex",
            task_type="generate_fix",
            data={
                "improvement": asdict(improvement),
                "instruction": self._build_codex_instruction(improvement)
            }
        )

        result = await delegate_to_codex(task)

        if "error" not in result:
            # Parse Codex response and update improvement
            improvement.changes = self._parse_codex_response(result["result"])

        return improvement

    def _build_codex_instruction(self, improvement: Improvement) -> str:
        """Build instruction for Codex based on improvement type."""
        if improvement.type == ImprovementType.NEW_ENDPOINT:
            return f"""Generate JavaScript fetch function and Python parser for:
Pattern: {improvement.analysis.get('pattern')}
Method: {improvement.analysis.get('method')}
Response keys: {improvement.analysis.get('response_keys')}

Output format:
1. JavaScript function for extension/activeFetcher.js
2. Python parser for backend/vascular_parser.py"""

        elif improvement.type == ImprovementType.PARSE_ERROR:
            return f"""Fix this parsing error:
{improvement.analysis}

Generate the corrected code with proper null checks."""

        elif improvement.type == ImprovementType.SCHEMA_CHANGE:
            return f"""Update parser for schema changes:
{improvement.analysis.get('field_changes')}

Generate updated parser code with field mapping."""

        return f"Generate code fix for: {improvement.description}"

    def _parse_codex_response(self, response: str) -> List[FileChange]:
        """Parse Codex response into FileChange objects."""
        changes = []

        # Simple parser - look for code blocks with file paths
        import re
        blocks = re.findall(r'```(\w+)?\n(.*?)```', response, re.DOTALL)

        for lang, code in blocks:
            # Try to extract file path from comments
            file_match = re.search(r'#\s*File:\s*(.+)|//\s*File:\s*(.+)', code)
            if file_match:
                file_path = file_match.group(1) or file_match.group(2)
                changes.append(FileChange(
                    file_path=file_path.strip(),
                    action="modify",
                    line_number=None,
                    old_content=None,
                    new_content=code,
                    description=f"Generated {lang} code"
                ))

        return changes

    # ==================== APPLY ====================

    def _save_improvement(self, improvement: Improvement) -> str:
        """Save improvement to pending directory."""
        file_path = self.improvements_dir / "pending" / f"{improvement.id}.json"

        with open(file_path, 'w') as f:
            json.dump(asdict(improvement), f, indent=2)

        # Also save markdown version for human review
        self._save_markdown(improvement)

        return improvement.id

    def _save_markdown(self, improvement: Improvement):
        """Save human-readable markdown version."""
        md_path = self.improvements_dir / "pending" / f"{improvement.id}.md"

        content = f"""# Improvement: {improvement.title}

**Type:** {improvement.type.value}
**Priority:** {improvement.priority.value}
**Confidence:** {improvement.confidence:.0%}
**Generated:** {improvement.created_at}
**Agent:** {improvement.agent}

## Analysis

{json.dumps(improvement.analysis, indent=2)}

## Proposed Changes

"""
        for change in improvement.changes:
            content += f"""### File: {change.file_path}

**Action:** {change.action}
{f"**Line:** {change.line_number}" if change.line_number else ""}

```
{change.new_content}
```

{change.description}

"""

        content += """## Actions

- [ ] Review changes
- [ ] Apply to codebase
- [ ] Test with sample data
"""

        with open(md_path, 'w') as f:
            f.write(content)

    def list_pending(self) -> List[Improvement]:
        """List all pending improvements."""
        improvements = []
        for file_path in (self.improvements_dir / "pending").glob("*.json"):
            with open(file_path) as f:
                data = json.load(f)
                improvements.append(Improvement(**data))
        return sorted(improvements, key=lambda x: x.created_at, reverse=True)

    def get_improvement(self, improvement_id: str) -> Optional[Improvement]:
        """Get a specific improvement by ID."""
        for status in ["pending", "applied", "rejected"]:
            file_path = self.improvements_dir / status / f"{improvement_id}.json"
            if file_path.exists():
                with open(file_path) as f:
                    data = json.load(f)
                    return Improvement(**data)
        return None

    def apply_improvement(self, improvement_id: str) -> bool:
        """Apply an improvement to the codebase."""
        improvement = self.get_improvement(improvement_id)
        if not improvement or improvement.status != ImprovementStatus.PENDING:
            return False

        # Apply each change
        for change in improvement.changes:
            self._apply_change(change)

        # Move to applied
        improvement.status = ImprovementStatus.APPLIED
        improvement.applied_at = datetime.now().isoformat()

        self._move_improvement(improvement, "pending", "applied")
        return True

    def reject_improvement(self, improvement_id: str, reason: str = "") -> bool:
        """Reject an improvement."""
        improvement = self.get_improvement(improvement_id)
        if not improvement or improvement.status != ImprovementStatus.PENDING:
            return False

        improvement.status = ImprovementStatus.REJECTED
        improvement.rejected_reason = reason

        self._move_improvement(improvement, "pending", "rejected")
        return True

    def _apply_change(self, change: FileChange):
        """Apply a single file change."""
        file_path = self.base_dir / change.file_path

        if change.action == "add":
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(change.new_content)

        elif change.action == "modify":
            if not file_path.exists():
                return

            with open(file_path, 'r') as f:
                content = f.read()

            if change.line_number and change.old_content:
                # Replace specific line
                lines = content.split('\n')
                if 0 < change.line_number <= len(lines):
                    lines[change.line_number - 1] = change.new_content
                    content = '\n'.join(lines)
            else:
                # Append to file
                content += '\n' + change.new_content

            with open(file_path, 'w') as f:
                f.write(content)

    def _move_improvement(self, improvement: Improvement, from_dir: str, to_dir: str):
        """Move improvement between directories."""
        from_path = self.improvements_dir / from_dir / f"{improvement.id}.json"
        to_path = self.improvements_dir / to_dir / f"{improvement.id}.json"

        with open(to_path, 'w') as f:
            json.dump(asdict(improvement), f, indent=2)

        from_path.unlink()

        # Also move markdown
        md_from = self.improvements_dir / from_dir / f"{improvement.id}.md"
        md_to = self.improvements_dir / to_dir / f"{improvement.id}.md"
        if md_from.exists():
            md_from.rename(md_to)


# ============================================================
# CLI INTERFACE
# ============================================================

def main():
    """CLI for improvement engine."""
    import sys

    engine = ImprovementEngine()

    if len(sys.argv) < 2:
        print("Usage: python -m backend.improvement_engine <command> [args]")
        print("\nCommands:")
        print("  list              List pending improvements")
        print("  show <id>         Show improvement details")
        print("  apply <id>        Apply improvement")
        print("  reject <id>       Reject improvement")
        return

    command = sys.argv[1]

    if command == "list":
        improvements = engine.list_pending()
        print(f"\n{'ID':<15} {'Type':<15} {'Priority':<10} {'Title':<40}")
        print("-" * 80)
        for imp in improvements:
            print(f"{imp.id:<15} {imp.type.value:<15} {imp.priority.value:<10} {imp.title[:40]}")

    elif command == "show" and len(sys.argv) > 2:
        imp = engine.get_improvement(sys.argv[2])
        if imp:
            print(f"\n{imp.title}")
            print(f"Type: {imp.type.value}")
            print(f"Priority: {imp.priority.value}")
            print(f"Confidence: {imp.confidence:.0%}")
            print(f"\nAnalysis:\n{json.dumps(imp.analysis, indent=2)}")
        else:
            print("Improvement not found")

    elif command == "apply" and len(sys.argv) > 2:
        if engine.apply_improvement(sys.argv[2]):
            print(f"Applied: {sys.argv[2]}")
        else:
            print("Failed to apply")

    elif command == "reject" and len(sys.argv) > 2:
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        if engine.reject_improvement(sys.argv[2], reason):
            print(f"Rejected: {sys.argv[2]}")
        else:
            print("Failed to reject")

if __name__ == "__main__":
    main()
