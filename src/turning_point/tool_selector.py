"""Dynamic Tool Selection Optimization Layer.

Scores available MCP tools against the user's query and active conversation context,
filtering down to the top N most relevant tools before passing them to the LLM.
This prevents context bloat and model confusion when dealing with hundreds of tools.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from .logger import get_logger
from .tool_converter import convert_all_tools

log = get_logger("tool_selector")

# Domain keyword aliases for boost scoring
DOMAIN_ALIASES: Dict[str, Set[str]] = {
    "queue": {"queue", "queues", "endpoint", "endpoints", "spool"},
    "client": {"client", "clients", "connection", "connections", "txflow", "rxflow", "session"},
    "vpn": {"vpn", "vpns", "msgvpn", "msgvpns"},
    "broker": {"broker", "about", "system", "health", "cert", "authority"},
    "domain": {"domain", "domains", "applicationdomain", "applicationdomains"},
    "application": {"application", "applications", "app", "apps", "applicationversion"},
    "eventapiproduct": {"eventapiproduct", "eventapiproducts", "eventapiproductversion", "eventapiproductversions"},
    "eventapi": {"eventapi", "eventapis", "eventapiversion", "eventapiversions"},
    "event": {"event", "events", "eventversion", "eventversions"},
    "schema": {"schema", "schemas", "schemaversion", "payload"},
    "rest": {"rest", "delivery", "rdo"},
    "acl": {"acl", "permission"},
}


def _stem(word: str) -> str:
    """Normalize plural/inflected English terms for token matching."""
    w = word.lower()
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("es") and not w.endswith("ses"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


def _tokenize(text: str) -> Set[str]:
    """Tokenize text into lowercase alphanumeric words, including stemmed variants."""
    if not text:
        return set()
    camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    words = re.findall(r"[a-zA-Z0-9]+", camel_split.lower())
    tokens = set()
    for w in words:
        tokens.add(w)
        tokens.add(_stem(w))
    return tokens


def score_tool(
    tool: Any,
    query_tokens: Set[str],
    raw_query: str,
    history_tool_names: Set[str],
) -> float:
    """Calculate relevance score of a tool for a given query."""
    tool_name = getattr(tool, "name", str(tool))
    tool_desc = getattr(tool, "description", "") or ""
    tool_tags = getattr(tool, "tags", []) or []

    score = 0.0

    # 1. Active conversation history retention
    if tool_name in history_tool_names:
        score += 1000.0

    name_tokens = _tokenize(tool_name)
    desc_tokens = _tokenize(tool_desc)
    tag_tokens: Set[str] = set()
    for t in tool_tags:
        tag_tokens.update(_tokenize(str(t)))

    raw_query_lower = raw_query.lower()
    tool_name_lower = tool_name.lower()

    # 2. Multi-word phrase precision matching
    if "event api product" in raw_query_lower or "event api products" in raw_query_lower:
        if "apiproduct" in tool_name_lower or "api_product" in tool_name_lower:
            score += 250.0
        elif "eventapi" in tool_name_lower:
            score += 30.0
    elif "event api" in raw_query_lower or "event apis" in raw_query_lower:
        if "apiproduct" in tool_name_lower:
            score += 50.0
        elif "eventapi" in tool_name_lower:
            score += 250.0
    elif "event" in raw_query_lower or "events" in raw_query_lower:
        if "apiproduct" not in tool_name_lower and "eventapi" not in tool_name_lower and "event" in tool_name_lower:
            score += 100.0

    # 3. Direct string / substring match in tool name
    for q_token in query_tokens:
        if len(q_token) < 2:
            continue

        if q_token in name_tokens:
            score += 50.0

        if q_token in tool_name_lower:
            score += 30.0

        if q_token in desc_tokens:
            score += 10.0

        if q_token in tag_tokens:
            score += 20.0

    # 4. Domain alias expansion boost
    for domain_key, aliases in DOMAIN_ALIASES.items():
        if any(alias in raw_query_lower for alias in aliases):
            if any(alias in tool_name_lower for alias in aliases):
                score += 40.0

    # Explicit domain prefix boosts for runtime broker objects
    if "queue" in raw_query_lower or "queues" in raw_query_lower:
        if "msgvpnqueue" in tool_name_lower or "msg_vpn_queue" in tool_name_lower:
            score += 100.0
    if "client" in raw_query_lower or "clients" in raw_query_lower:
        if "msgvpnclient" in tool_name_lower or "clientusername" in tool_name_lower:
            score += 100.0
    if "acl" in raw_query_lower:
        if "aclprofile" in tool_name_lower:
            score += 100.0

    # 5. Action verb alignment boost (create vs get vs update vs delete)
    create_keywords = {"create", "add", "make", "new", "duplicate", "build"}
    read_keywords = {"get", "list", "show", "view", "find", "read", "fetch", "check", "display"}
    update_keywords = {"update", "patch", "modify", "change", "edit", "add", "remove"}
    delete_keywords = {"delete", "remove", "destroy", "clear"}

    if any(ck in raw_query_lower for ck in create_keywords):
        if tool_name_lower.startswith("create"):
            score += 40.0
    if any(rk in raw_query_lower for rk in read_keywords):
        if tool_name_lower.startswith("get") or "list" in tool_name_lower:
            score += 20.0
    if any(uk in raw_query_lower for uk in update_keywords):
        if tool_name_lower.startswith("update") or tool_name_lower.startswith("patch"):
            score += 30.0
    if any(dk in raw_query_lower for dk in delete_keywords):
        if tool_name_lower.startswith("delete"):
            score += 40.0

    return score


def classify_intent(query: str) -> str:
    """Middle Layer Router: classify user prompt into strict intent category."""
    q = query.lower()
    if any(p in q for p in ["event api product", "event api products", "api product", "api products"]):
        return "EVENT_API_PRODUCT"
    if any(p in q for p in ["event api", "event apis"]) or ("api" in q and "event" in q and "product" not in q):
        return "EVENT_API"
    if ("event" in q or "events" in q) and not any(p in q for p in ["product", "api"]):
        return "EVENT"
    if any(k in q for k in ["queue", "queues", "subscription", "subscriptions", "ttl", "spool"]):
        return "QUEUE"
    if any(k in q for k in ["client", "clients", "acl", "connection", "connections", "clientusername"]):
        return "CLIENT_ACL"
    if any(k in q for k in ["application", "applications", "app", "apps", "consumer", "consumers"]):
        return "APPLICATION"
    if any(k in q for k in ["schema", "schemas", "payload"]):
        return "SCHEMA"
    return "GENERAL"


def is_tool_allowed_for_intent(tool_name: str, intent: str) -> bool:
    """Middle Layer Router: strict filter logic ensuring only relevant tools are passed."""
    tn = tool_name.lower()
    if intent == "EVENT_API_PRODUCT":
        if "apiproduct" in tn or "api_product" in tn:
            return True
        if tn in {"getapplicationdomains", "getapplicationdomain", "geteventapis", "geteventapi", "geteventapiversions"}:
            return True
        return False

    if intent == "EVENT_API":
        if "apiproduct" in tn:
            return False
        if "eventapi" in tn:
            return True
        if tn in {"getapplicationdomains", "getapplicationdomain", "getconsumers", "getconsumer", "getevents", "geteventversions", "getschemas", "getschemaversions"}:
            return True
        return False

    if intent == "EVENT":
        if "eventapi" in tn or "apiproduct" in tn:
            return False
        if "event" in tn:
            return True
        if tn in {"getapplicationdomains", "getapplicationdomain", "getschemas", "getschemaversions"}:
            return True
        return False

    if intent == "QUEUE":
        if any(k in tn for k in ["queue", "subscription", "msgvpnqueue"]):
            return True
        return False

    if intent == "CLIENT_ACL":
        if any(k in tn for k in ["client", "acl", "connection", "username", "msgvpnclient"]):
            return True
        return False

    if intent == "APPLICATION":
        if any(k in tn for k in ["application", "consumer"]):
            return True
        if tn in {"getapplicationdomains", "getapplicationdomain"}:
            return True
        return False

    if intent == "SCHEMA":
        if "schema" in tn or tn in {"getapplicationdomains", "getapplicationdomain"}:
            return True
        return False

    return True


def select_relevant_tools(
    all_tools: List[Any],
    user_query: str,
    max_tools: int = 30,
    history_tool_names: Optional[Set[str]] = None,
) -> Tuple[List[Dict[str, Any]], List[Any]]:
    """Middle Layer Tool Router: Select and route the exact tools required for user query.

    Args:
        all_tools: Complete list of discovered MCP tool objects.
        user_query: The user's prompt text.
        max_tools: Maximum number of tools to select (default 30).
        history_tool_names: Set of tool names executed previously in conversation.

    Returns:
        Tuple of (ollama_formatted_tools, selected_mcp_tools)
    """
    if not all_tools:
        return [], []

    if history_tool_names is None:
        history_tool_names = set()

    # 1. Classify prompt intent
    intent = classify_intent(user_query)
    log.info("Middle Layer Tool Router: Prompt intent classified as '%s' for query '%s'", intent, user_query[:50])

    # 2. Strict candidate filtering per intent category
    candidate_tools = []
    for tool in all_tools:
        tool_name = getattr(tool, "name", str(tool))
        if tool_name in history_tool_names or is_tool_allowed_for_intent(tool_name, intent):
            candidate_tools.append(tool)

    if not candidate_tools:
        candidate_tools = all_tools

    # If total candidate tools are within max_tools limit, return all candidates directly
    if len(candidate_tools) <= max_tools:
        log.info(
            "Middle Layer Router: Candidate pool (%d tools) <= max limit (%d); routing all candidates directly",
            len(candidate_tools),
            max_tools,
        )
        ollama_tools = convert_all_tools(candidate_tools)
        return ollama_tools, candidate_tools

    query_tokens = _tokenize(user_query)

    # 3. Score candidate tools
    scored_tools = []
    for tool in candidate_tools:
        score = score_tool(tool, query_tokens, user_query, history_tool_names)
        scored_tools.append((score, tool))

    # Sort descending by score
    scored_tools.sort(key=lambda x: x[0], reverse=True)

    selected_mcp_tools = [t[1] for t in scored_tools[:max_tools]]

    ollama_tools = convert_all_tools(selected_mcp_tools)
    selected_names = [getattr(t, "name", str(t)) for t in selected_mcp_tools]

    log.info(
        "Middle Layer Tool Router: Routed %d / %d tools for query '%s' (Intent: %s)",
        len(selected_mcp_tools),
        len(all_tools),
        user_query[:50],
        intent,
    )
    log.debug("Routed tools: %s", ", ".join(selected_names))

    return ollama_tools, selected_mcp_tools
