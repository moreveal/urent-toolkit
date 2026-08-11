from __future__ import annotations

import json
import random
import tempfile
import unittest
from pathlib import Path

from urent_toolkit.device import create_persona
from urent_toolkit.profiles import ANDROID_PROFILES, choose_profile, webview_fingerprint


class AndroidProfilesTest(unittest.TestCase):
    def test_generated_user_agent_is_coherent(self) -> None:
        profile = choose_profile("pixel-8")
        user_agent = profile.webview_user_agent
        self.assertIn("Android 14", user_agent)
        self.assertIn("Pixel 8", user_agent)
        self.assertIn("Chrome/124.0.6367.179", user_agent)
        self.assertIn("Mobile Safari/537.36", user_agent)

    def test_default_selection_uses_the_supplied_rng(self) -> None:
        first = choose_profile(rng=random.Random(7))
        second = choose_profile(rng=random.Random(7))
        self.assertEqual(first, second)
        self.assertIn(first, ANDROID_PROFILES)

    def test_fingerprint_matches_profile(self) -> None:
        profile = choose_profile("galaxy-s22")
        value = json.loads(webview_fingerprint(profile, "ru-RU", "GMT+3"))
        self.assertEqual(value["screen"]["screenWidth"], profile.screen_width)
        self.assertEqual(value["userAgent"], profile.webview_user_agent)
        self.assertEqual(value["timezone"]["timezone"], -180)

    def test_personas_are_ephemeral_by_default(self) -> None:
        first, _ = create_persona("pixel-7")
        second, _ = create_persona("pixel-7")
        self.assertNotEqual(first.device_id, second.device_id)
        self.assertNotEqual(first.appsflyer_id, second.appsflyer_id)

    def test_device_file_persists_the_complete_persona(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phone.json"
            first_identity, first_profile = create_persona("redmi-note-12", device_file=path)
            second_identity, second_profile = create_persona(device_file=path)
            self.assertEqual(first_identity.device_id, second_identity.device_id)
            self.assertEqual(first_identity.appsflyer_id, second_identity.appsflyer_id)
            self.assertEqual(first_profile, second_profile)
            self.assertNotEqual(first_identity.session_id, second_identity.session_id)

    def test_legacy_device_file_can_be_migrated_with_explicit_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.device.json"
            path.write_text(
                json.dumps(
                    {
                        "device_id": "legacy-device",
                        "appsflyer_id": "legacy-appsflyer",
                    }
                ),
                encoding="utf-8",
            )

            identity, profile = create_persona("pixel-8", device_file=path)
            stored = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(identity.device_id, "legacy-device")
            self.assertEqual(identity.appsflyer_id, "legacy-appsflyer")
            self.assertEqual(profile.id, "pixel-8")
            self.assertEqual(stored["profile"]["id"], "pixel-8")


if __name__ == "__main__":
    unittest.main()
