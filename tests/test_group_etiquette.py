import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from group_etiquette import Action, GroupEtiquette, Roster, addressees, is_bare_ack  # noqa: E402

ROSTER = Roster.from_config({
    "self": {"name": "Hermes", "aliases": ["hermes"]},
    "members": [
        {"name": "Sam", "role": "owner", "handles": ["+15550000001", "sam@example.com"], "aliases": ["sam"]},
        {"name": "Iris", "role": "agent", "handles": ["+15550000002"], "aliases": ["iris", "personal iris"],
         "about": "the owner's personal agent"},
        {"name": "Group Iris", "role": "agent", "handles": ["+15550000003"], "aliases": ["group iris"],
         "about": "Iris's group persona"},
    ],
})
OWNER, IRIS, GROUP_IRIS, STRANGER = "+15550000001", "+15550000002", "tel:+15550000003", "+15559999999"
CHAT = "group-1"


def to(text, reply_to=None):
    return sorted(addressees(text, ROSTER, reply_to))


class Addressing(unittest.TestCase):
    def test_screenshot_lines(self):
        self.assertEqual(to("Group iris ask my personal iris to confirm you can coordinate with it"), ["Group Iris"])
        self.assertEqual(to("Hermes, this is a group chat with you and Iris And me"), ["Hermes"])
        self.assertEqual(to("iris for you too"), ["Iris"])
        self.assertEqual(to("Iris you still here?"), ["Iris"])
        self.assertEqual(to("hey iris"), ["Iris"])
        self.assertEqual(to("test"), [])

    def test_two_at_once(self):
        self.assertEqual(to("Iris, find the address. Hermes, start the lane"), ["Hermes", "Iris"])

    def test_object_position_is_not_address(self):
        self.assertEqual(to("ask iris for the address"), [])
        self.assertEqual(to("can you check with hermes"), [])

    def test_closing_vocative(self):
        self.assertEqual(to("what's running right now, hermes?"), ["Hermes"])

    def test_name_inside_a_word_is_not_a_name(self):
        self.assertEqual(to("hermesian logic, irises in bloom"), [])

    def test_reply_thread_addresses_the_author(self):
        self.assertEqual(to("yes that one", ROSTER.me), ["Hermes"])


class Acks(unittest.TestCase):
    def test_acks(self):
        for t in ["ok", "Got it.", "thanks!", "sounds good", "👍", "will do thanks"]:
            self.assertTrue(is_bare_ack(t), t)
        for t in ["ok, what's next?", "got it, but the lane failed at step 3", "can you check?"]:
            self.assertFalse(is_bare_ack(t), t)


class Decisions(unittest.TestCase):
    def setUp(self):
        self.g = GroupEtiquette(ROSTER, agent_turns_per_owner_message=2, agent_turn_cap=3, window_ms=1000)

    def d(self, handle, text, t, **kw):
        return self.g.decide(CHAT, handle, text, now_ms=t, **kw)

    def test_stranger_dropped(self):
        self.assertIs(self.d(STRANGER, "hermes do this", 0).action, Action.DROP)

    def test_owner_always_gets_a_turn_and_silence_is_allowed_unless_named(self):
        a = self.d(OWNER, "Group iris ask my personal iris to confirm you can coordinate with it", 0)
        self.assertEqual((a.action, a.reply_expected), (Action.TURN, False))
        self.assertIn("not you", a.hint)
        b = self.d(OWNER, "Hermes, this is a group chat with you and Iris And me", 1)
        self.assertEqual((b.action, b.reply_expected), (Action.TURN, True))
        c = self.d(OWNER, "test", 2)
        self.assertEqual((c.action, c.reply_expected), (Action.TURN, False))
        self.assertIn("decide from context", c.hint)

    def test_agent_turns_are_budgeted_per_owner_message(self):
        self.d(OWNER, "hermes, ask iris for the address", 0)
        self.assertIs(self.d(IRIS, "hermes, it's 12 Main St", 1).action, Action.TURN)
        self.assertIs(self.d(IRIS, "hermes, want the zip too?", 2).action, Action.TURN)
        spent = self.d(IRIS, "hermes, anything else?", 3)
        self.assertEqual((spent.action, spent.why), (Action.CONTEXT, "agent turn budget for this owner message spent"))
        self.d(OWNER, "thanks both", 4)
        self.assertIs(self.d(IRIS, "hermes, one more thing", 5).action, Action.TURN)

    def test_window_cap_stops_slow_ping_pong(self):
        self.d(OWNER, "go", 0)
        self.d(IRIS, "hermes a", 1)
        self.d(IRIS, "hermes b", 2)
        self.d(OWNER, "go", 3)
        self.d(GROUP_IRIS, "hermes c", 4)
        self.assertEqual(self.d(GROUP_IRIS, "hermes d", 5).why, "agent turn cap for the window reached")
        self.assertIs(self.d(GROUP_IRIS, "hermes e", 1002).action, Action.TURN)

    def test_agent_ack_becomes_context_and_drains_once(self):
        self.d(OWNER, "iris, check the calendar", 0)
        self.assertIs(self.d(IRIS, "got it", 1).action, Action.CONTEXT)
        self.assertEqual(self.g.drain_context(CHAT), "[Earlier in this group, no reply was needed]\n[Iris] got it")
        self.assertIsNone(self.g.drain_context(CHAT))

    def test_agent_reply_to_own_message_is_addressed(self):
        self.g.observe("m1", ROSTER.me)
        dec = self.d(IRIS, "done, it's booked", 1, reply_to_guid="m1")
        self.assertEqual((dec.action, sorted(dec.addressed), dec.reply_expected), (Action.TURN, ["Hermes"], False))

    def test_system_prompt_lists_members_and_rules(self):
        p = self.g.system_prompt()
        self.assertIn("- Iris (agent): the owner's personal agent", p)
        self.assertIn("Never announce that you are staying out", p)


if __name__ == "__main__":
    unittest.main()
