# Wiring it into the Hermes BlueBubbles adapter

Hermes already has the hooks this needs. A `MessageEvent` carries three fields that do the work:

| Field | What it does here |
| --- | --- |
| `reply_expected` | `False` lets the agent answer with the silence marker and stay silent. Hermes keeps quiet with no warning and no forced follow-up turn. |
| `channel_prompt` | A per-channel system prompt for that turn only. It is never saved. The roster and the rules go here. |
| `channel_context` | Lines placed before the new message. The addressing hint and any buffered lines go here. |

The steps below assume `gateway/platforms/bluebubbles.py`. Other adapters follow the same shape.

## 1. Vendor the module

Copy `src/group_etiquette/__init__.py` to `gateway/platforms/group_etiquette.py`. It has no dependencies.

## 2. Build it from config

```python
from .group_etiquette import Action, GroupEtiquette, Roster

# in __init__
roster = extra.get("group_roster")
self._etiquette = GroupEtiquette(Roster.from_config(roster)) if isinstance(roster, dict) else None
```

## 3. Record your own sends

When a webhook row is `isFromMe` in a group chat, remember it, so a threaded reply to it counts as addressed to you:

```python
if self._etiquette and ";+;" in (chat_id or ""):
    self._etiquette.observe(row_guid, self._etiquette.roster.me)
```

## 4. Decide before the mention gate

```python
decision = None
if is_group and self._etiquette:
    decision = self._etiquette.decide(chat_id, sender, text, now_ms=int(time.time() * 1000),
                                      guid=row_guid, reply_to_guid=record.get("threadOriginatorGuid"))
    if decision.action is not Action.TURN:
        return _ok()          # DROP: not on the roster. CONTEXT: kept for the next turn.
```

Skip the old `require_mention` check when `decision` is set, and use `decision.sender.name` as the event's
`user_name`, so the transcript reads `[Sam] ...` and not a phone number.

## 5. Fill the event

```python
if decision is not None:
    event.reply_expected = decision.reply_expected
    event.channel_prompt = self._etiquette.system_prompt()
    event.channel_context = "\n\n".join(
        p for p in (self._etiquette.drain_context(chat_id), f"(addressing hint: {decision.hint})") if p)
```

## 6. One bubble in groups

The adapter turns each blank-line paragraph into its own bubble. In a group, join them so a reply lands as
one message.

## 7. Config

```yaml
group_sessions_per_user: false      # one shared conversation per group, so the agent sees everyone

platforms:
  bluebubbles:
    extra:
      require_mention: false
      group_roster:
        self: {name: Hermes, aliases: [hermes], about: "Sam's work agent"}
        members:
          - {name: Sam, role: owner, handles: ["+15550000001"], aliases: [sam]}
          - {name: Iris, role: agent, handles: ["+15550000002"], aliases: [iris],
             about: "Sam's personal agent"}
```

Set `BLUEBUBBLES_REQUIRE_MENTION` in `.env` to the same value as `require_mention`. On the Hermes version this
was built against, the env pass rewrites `require_mention` from that variable, and an unset variable reads as
false. Without it, `require_mention: true` in YAML is silently ignored. See `docs/upstream-issue.md`.

## 8. Let other agents wait their turn

With one shared session per group, a line from another agent can arrive while your agent is still answering
the owner. Hermes's default `busy_input_mode: interrupt` would redirect the running turn. Tag group events
with the sender's role (`event.metadata["group_member_role"] = decision.sender.role.value`) and, in both
busy paths (`_resolve_busy_steer_or_redirect` and the priority path in `run_inbound.py`), demote `interrupt`
to `queue` when the role is `agent`. The owner's own mid-turn corrections still redirect.

## 9. No typing dots before a silence

A turn that may end in silence should not show "..." in the chat, or people wait for a message that never
comes. Skip `send_typing` for a chat while its current turn has `reply_expected = False`.
