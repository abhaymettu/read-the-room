# Draft upstream issue (not filed)

**Title.** BlueBubbles: `require_mention: true` in config.yaml is overwritten to false when `BLUEBUBBLES_REQUIRE_MENTION` is unset

**What happens.** With `platforms.bluebubbles.extra.require_mention: true` in `config.yaml` and no
`BLUEBUBBLES_REQUIRE_MENTION` in the environment, the adapter starts with `require_mention == False`. Every
group message reaches the agent, named or not.

**Why.** In `gateway/config_env.py`, the BlueBubbles `_Cred` entry lists `require_mention` under `fixed=`
with default `""`, parsed by `_truthy_token`. The env pass always writes that key into `extra`, so the empty
default replaces the YAML value. The comment beside it says so: "``require_mention`` is always written: an
unset env reads as "" -> False".

**Repro.**

1. Set `require_mention: true` under `platforms.bluebubbles.extra`, with `BLUEBUBBLES_SERVER_URL` and
   `BLUEBUBBLES_PASSWORD` set and `BLUEBUBBLES_REQUIRE_MENTION` unset.
2. `load_gateway_config().platforms[Platform.BLUEBUBBLES].extra["require_mention"]` returns `False`.
3. Set `BLUEBUBBLES_REQUIRE_MENTION=true`. It now returns `True`.

A wrapped group message also shows it. Hermes receives "Hermes, hi" with the wake word still attached, which
means `_clean_mention_text` never ran.

**Suggested fix.** Move `require_mention` from `fixed=` to `optional=` so an unset env leaves the YAML value
alone, or write it only when the YAML has no value.
