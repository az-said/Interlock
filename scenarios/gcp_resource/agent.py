"""
The SRE agent: a real model over the Anthropic Messages API (urllib, like backend/agent.py). It reads the
live config object through get_config and must answer with rollback_config. It never writes; it returns
the decision, validated here, including the generation it read (the fact the decision rests on).

Reads ANTHROPIC_API_KEY from the environment. INTERLOCK_MODEL picks the model.
"""
import json, os, time, urllib.error, urllib.request

MODEL = os.environ.get("INTERLOCK_MODEL", "claude-haiku-4-5-20251001")
APPROVED = "v41"


def _config(version, new_checkout, **extra):
    return json.dumps({"version": version, "new_checkout": new_checkout, "timeout_ms": 800, **extra}, sort_keys=True)


CONFIGS = {
    "v41": _config("v41", False),                                           # known good, the approved rollback
    "v42": _config("v42", True),                                            # the bad deploy the incident is about
    "v43": _config("v43", True, fix="guard null cart in checkout"),         # the human's redeploy during the outage
}
SYSTEM = ("You are an SRE agent working an incident. Read the live config with get_config, then call "
          "rollback_config exactly once with the version the incident approves.")
TOOLS = [
    {"name": "get_config", "description": "The live config object: its GCS generation, content, and who deployed it.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "rollback_config", "description": "Overwrite the live config object with a known-good version.",
     "input_schema": {"type": "object", "required": ["to_version", "reason"],
                      "properties": {"to_version": {"type": "string"}, "reason": {"type": "string"}}}},
]


class AgentError(RuntimeError):
    pass


def validate(args, approved=APPROVED):
    """The trust boundary: the model's tool call is untrusted input and may only pick the approved version."""
    version, reason = args.get("to_version"), args.get("reason")
    if version != approved:
        raise AgentError(f"to_version {version!r} is not the approved rollback {approved!r}")
    if not isinstance(reason, str) or not reason.strip():
        raise AgentError("reason must be a non-empty string")
    return {"to_version": version, "reason": reason.strip()[:300]}


def _call(body):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise AgentError("ANTHROPIC_API_KEY is not set")
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(), method="POST",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                          "content-type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 529) or attempt == 3:
                raise AgentError(f"Anthropic API {e.code}: {e.read()[:300]!r}") from None
            time.sleep(2 ** attempt)


def decide(client, bucket, name, incident):
    """Run the model until it calls rollback_config after reading. Returns the decision and the generation it saw."""
    messages, seen = [{"role": "user", "content": f"Incident:\n{incident}"}], None
    for _ in range(4):
        resp = _call({"model": MODEL, "max_tokens": 1024, "system": SYSTEM, "tools": TOOLS,
                      "tool_choice": {"type": "any"}, "messages": messages})
        calls = [b for b in resp["content"] if b["type"] == "tool_use"]
        rollback = next((c for c in calls if c["name"] == "rollback_config"), None)
        if rollback and seen:
            return {**validate(rollback["input"]), "generation": seen["generation"], "model": resp["model"],
                    "tool_call": rollback["input"]}
        results = []
        for c in calls:
            if c["name"] == "get_config":
                live = client.get(bucket, name)
                seen = {"generation": live["generation"], "deployed_by": live.get("metadata", {}).get("writer"),
                        "content": client.read(bucket, name)}
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(seen)})
            else:
                results.append({"type": "tool_result", "tool_use_id": c["id"], "is_error": True,
                                "content": "read the live config with get_config first"})
        messages += [{"role": "assistant", "content": resp["content"]}, {"role": "user", "content": results}]
    raise AgentError("the model never called rollback_config after reading the config")
