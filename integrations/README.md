# Wiring it into any agent

read-the-room doesn't know or care which chat app it runs in. It needs four things from your gateway, the
code that receives messages from the platform and calls the model.

## The contract

1. **Decide on every group message.** Before any wake-word or mention check, call

   ```python
   d = etiquette.decide(chat_id, sender_id, text, now_ms=now_ms, guid=message_id, reply_to_guid=replied_to_id)
   ```

   `DROP` means the sender isn't on the roster, so ignore it. `CONTEXT` means do nothing: the line is buffered
   and reaches the agent with its next turn. `TURN` means run the model.
2. **Give the model the room.** On a `TURN`, put `etiquette.system_prompt()` in the system or channel prompt
   for that turn, and put `etiquette.drain_context(chat_id)` and `d.hint` before the new message.
3. **Let silence be silence.** When `d.reply_expected` is `False` and the model answers with your silence
   marker (`NO_REPLY`, an empty string, whatever your agent uses), send nothing. Check every "retry if
   empty" or "a human must get a reply" path in your gateway. Those are what make agents announce that
   they're staying out.
4. **Remember your own sends.** Call `etiquette.observe(sent_message_id, etiquette.roster.me)` after the
   agent posts, so a threaded reply to it counts as addressed to the agent.

Turn off the platform's own mention gate for these chats. The roster already keeps strangers out, and the
agent needs every message from members to follow the thread.

## What to pass, per platform

Roster `handles` are the same ids you pass as `sender_id`. Put the agent's own platform id in
`self.handles` so `<@id>` mention tokens resolve to it.

| Platform | `sender_id` | `reply_to_guid` | Mentions it reads |
| --- | --- | --- | --- |
| iMessage (BlueBubbles) | handle address, `+1555...` or an email | `threadOriginatorGuid` | names |
| WhatsApp | sender JID, `1555...@s.whatsapp.net` (matches a `+1555...` roster handle) | id of the quoted message | names, `@name` |
| Telegram | `from.id` | `reply_to_message.message_id` | names, `@username` (add it to `aliases`) |
| Discord | `author.id` | `message_reference.message_id` | names, `<@id>`, `<@!id>` |
| Slack | user id, `U...` | the parent message `ts` | names, `<@U...>` |
| Signal | sender number or UUID | `quote.id` | names |

## Worked example

[`hermes-bluebubbles`](hermes-bluebubbles/README.md) wires it into Hermes Agent's iMessage adapter, which is
where it runs in production. Every Hermes platform adapter builds the same `MessageEvent` with
`reply_expected`, `channel_prompt` and `channel_context`, so the same steps carry over to its WhatsApp,
Telegram, Discord, Slack and Signal adapters.
