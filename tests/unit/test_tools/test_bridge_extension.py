"""Tests for bridge extension."""

class TestBridgeExtension:
    def test_new_commands_registered(self):
        from school.bridge import _COMMANDS
        new_commands = [
            "learn", "diagnose", "conflict", "confidence",
            "deduplicate", "lifecycle", "search", "knowledge",
        ]
        for cmd in new_commands:
            assert cmd in _COMMANDS, f"Command '{cmd}' not in _COMMANDS"

    def test_existing_commands_preserved(self):
        from school.bridge import _COMMANDS
        assert "status" in _COMMANDS
        assert "remember" in _COMMANDS
        assert "recall" in _COMMANDS
