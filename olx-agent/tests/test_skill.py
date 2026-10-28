"""The skill shipped with the plugin is also the source of the API agent's system prompt and of the guides."""

import re

from olx_agent.guides import GUIDES_DIR, SKILL_DIR, TOPICS, get_guide
from olx_agent.prompts import SYSTEM_PROMPT, skill_body
from olx_agent.tools import ToolContext, build_tools


def _frontmatter():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with YAML frontmatter"
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    return fields


def test_frontmatter_is_valid_for_claude_apps():
    fields = _frontmatter()
    assert set(fields) == {"name", "description"}
    assert fields["name"] == SKILL_DIR.name == "olx-zakupy"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", fields["name"])
    assert 200 < len(fields["description"]) <= 1024
    assert "<" not in fields["description"] and ">" not in fields["description"]


def test_every_guide_topic_has_a_file_and_vice_versa():
    files = {p.stem for p in GUIDES_DIR.glob("*.md")}
    assert files == set(TOPICS)
    assert get_guide("phones").startswith("# Telefony")
    assert get_guide("nonexistent") == get_guide("general")
    for topic in TOPICS:
        assert f"{topic}" in skill_body()  # the skill lists every topic for tool-less use


def test_skill_names_every_tool(config, olx):
    names = [t.name for t in build_tools(ToolContext(config, olx, None, None))]
    body = skill_body()
    missing = [n for n in names if f"`{n}`" not in body]
    assert not missing


def test_api_system_prompt_is_built_from_the_skill():
    body = skill_body()
    assert not body.startswith("---")
    assert body in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.startswith("Jesteś Agentem OLX")
