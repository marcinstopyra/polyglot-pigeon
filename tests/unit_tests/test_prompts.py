import pytest
import yaml

from polyglot_pigeon.prompts import PromptManager


class TestPromptManager:
    """Test PromptManager loading, overrides, and placeholder substitution."""

    def test_loads_defaults(self):
        manager = PromptManager()
        prompts = manager.list_prompts()

        assert "system" in prompts
        assert "transform_user" in prompts
        assert "json_fix" in prompts
        assert "language_extra" in prompts
        assert "tone_extra" in prompts
        assert "article_structure_extra" in prompts

    def test_get_with_placeholders(self):
        manager = PromptManager()
        result = manager.get(
            "system",
            known_language="English",
            target_language="German",
            level="B1",
            language_extra="",
            tone_extra="",
            article_structure_extra="",
            json_schema="{}",
        )

        assert "English" in result
        assert "German" in result
        assert "B1" in result

    def test_get_unknown_prompt_raises_key_error(self):
        manager = PromptManager()

        with pytest.raises(KeyError, match="nonexistent"):
            manager.get("nonexistent")

    def test_partial_override(self, tmp_path):
        override_file = tmp_path / "overrides.yaml"
        override_file.write_text(
            yaml.dump({"language_extra": "Use only present tense."})
        )

        manager = PromptManager(overrides_path=override_file)

        assert manager.get("language_extra") == "Use only present tense."
        # Other prompts still have defaults
        assert "system" in manager.list_prompts()

    def test_full_override_replaces_prompt(self, tmp_path):
        override_file = tmp_path / "overrides.yaml"
        override_file.write_text(yaml.dump({"system": "You are a custom assistant."}))

        manager = PromptManager(overrides_path=override_file)
        result = manager.get("system")

        assert result == "You are a custom assistant."

    def test_no_overrides(self):
        manager = PromptManager(overrides_path=None)
        prompts = manager.list_prompts()

        assert len(prompts) >= 4

    def test_language_extra_injected_into_system(self):
        manager = PromptManager()
        result = manager.get(
            "system",
            known_language="English",
            target_language="German",
            level="B1",
            language_extra="Avoid using Präteritum.",
            tone_extra="",
            article_structure_extra="",
            json_schema="{}",
        )

        assert "Avoid using Präteritum." in result

    def test_tone_extra_injected_into_system(self):
        manager = PromptManager()
        result = manager.get(
            "system",
            known_language="English",
            target_language="German",
            level="B1",
            language_extra="",
            tone_extra="Tell the news in a gossipy, informal tone.",
            article_structure_extra="",
            json_schema="{}",
        )

        assert "Tell the news in a gossipy, informal tone." in result

    def test_article_structure_extra_injected(self):
        manager = PromptManager()
        result = manager.get(
            "system",
            known_language="English",
            target_language="German",
            level="B1",
            language_extra="",
            tone_extra="",
            article_structure_extra="Include example sentences for each glossary word.",
            json_schema="{}",
        )

        assert "Include example sentences for each glossary word." in result

    def test_transform_user_with_content(self):
        manager = PromptManager()
        result = manager.get(
            "transform_user",
            content="Today in tech: AI advances continue.",
        )

        assert "Today in tech: AI advances continue." in result
