# tests/unit/test_school_skill.py
import re

from school.skill_source import ROUTING_SKILL_MD


def _frontmatter(md: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    assert m, "frontmatter missing"
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_frontmatter_valid():
    fm = _frontmatter(ROUTING_SKILL_MD)
    assert fm["name"] == "school-routing"
    assert re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", fm["name"])
    assert 1 <= len(fm["description"]) <= 1024
    assert "light" in fm["description"]


def test_workflow_has_three_actions():
    body = ROUTING_SKILL_MD
    assert "routing lessons" in body
    assert "routing.json" in body  # knobs
    assert "audit" in body
    assert "4 options" in body or "four options" in body  # calibration question


def test_install_writes_skill(tmp_path):
    from school.cli import install_skill

    out = install_skill(dest_root=str(tmp_path))
    assert out == tmp_path / "school-routing" / "SKILL.md"
    assert out.read_text(encoding="utf-8") == ROUTING_SKILL_MD
