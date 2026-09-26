import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lite_policy import check_request, enforce_settings


class LitePolicyTests(unittest.TestCase):
    def test_settings_cannot_enable_discord_or_qwen_in_lite(self):
        settings = {"qwen_mode": "fallback", "discord_commands_enabled": True}
        self.assertEqual(enforce_settings(dict(settings), False), settings)
        lite = enforce_settings(dict(settings), True)
        self.assertEqual(lite["qwen_mode"], "disabled")
        self.assertFalse(lite["discord_commands_enabled"])

    def test_lite_denies_unavailable_actions_before_dispatch(self):
        for action in ("bot", "voice_restart", "reply_mode", "members",
                       "logs", "training", "repair", "window", "unknown"):
            with self.subTest(action=action), self.assertRaises(PermissionError):
                check_request({"action": action}, True)
        for request in ({"action": "setting", "key": "qwen_mode", "value": "explicit"},
                        {"action": "setting", "key": "discord_commands_enabled", "value": True},
                        {"action": "name", "key": "friday"}):
            with self.assertRaises(PermissionError):
                check_request(request, True)

    def test_lite_local_features_and_full_edition_unchanged(self):
        for request in ({"action": "status"}, {"action": "macros"},
                        {"action": "voice_store"}, {"action": "stt_variants"}, {"action": "backup"},
                        {"action": "logs", "source": "jarvis"}, {"action": "window", "window": "chat"},
                        {"action": "console"}, {"action": "favorite"}, {"action": "startup"},
                        {"action": "diagnostics"}, {"action": "full_shutdown"},
                        {"action": "name", "key": "jarvis"},
                        {"action": "setting", "key": "voice_enabled", "value": True}):
            check_request(request, True)
        for action in ("bot", "console", "setting", "window", "full_shutdown"):
            check_request({"action": action}, False)
