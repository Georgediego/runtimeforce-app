"""
Fallback Regex Parser for extracting function calls from plain text outputs safely.
"""
import re
import json
import uuid
import logging
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("runtimeforce.service.agent.regex_fallback")

class AgentRegexFallbackParser:
    PAT = re.compile(r"<function\((?P<name>[a-zA-Z0-9_]+)\((?P<args>[\s\S]*?)\)\)>")

    @classmethod
    def parse(cls, text: str) -> Tuple[str, List[Dict[str, Any]]]:
        if not text or "<function(" not in text:
            return text, []

        matches = list(cls.PAT.finditer(text))
        if not matches:
            return text, []

        tool_calls = []
        for match in matches:
            name = match.group("name")
            args_raw = match.group("args").strip()
            parsed = {}
            if args_raw:
                try:
                    parsed = json.loads(args_raw)
                except Exception as e:
                    logger.debug(f"Regex fallback JSON decode warning for {name}: {e}")
                    parsed = {"raw": args_raw}

            tool_calls.append({
                "id": f"call_fb_{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(parsed, ensure_ascii=False),
                },
            })

        clean_text = cls.PAT.sub(" ", text).strip()
        return clean_text, tool_calls
