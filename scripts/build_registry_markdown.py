import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
data = json.loads((ROOT / "character-registry.json").read_text(encoding="utf-8"))
lines = [
    "# Persistent character registry",
    "",
    data["continuity_rule"],
    "",
    "## Canonical nurses",
    "",
]
for c in data["nurses"]:
    lines += [
        f"### {c['id']}", "",
        f"- Species: {c['species']}",
        f"- Palette: {', '.join(c['primary_colors'])}",
        f"- Eye color: {c['eye_color']}",
        f"- Body shape: {c['body_shape']}",
        f"- Locked identifier: {c['identifying_feature']}",
        f"- Personality: {c['personality']}",
        f"- Animation: {', '.join(c['animation_tendencies'])}", "",
    ]
lines += ["## Recurring fictional adult clients", ""]
for c in data["clients"]:
    lines += [
        f"### {c['id']} — {c['name']}", "",
        f"- Species: {c['species']}",
        f"- Scale pattern: {c['scale_pattern']}",
        f"- Palette: {', '.join(c['primary_colors'])}",
        f"- Eye color: {c['eye_color']}",
        f"- Body shape: {c['body_shape']}",
        f"- Locked identifier: {c['identifying_feature']}",
        f"- Early detox: {c['detox_appearance']}",
        f"- Stabilizing: {c['stabilization_appearance']}",
        f"- Residential: {c['residential_appearance']}",
        f"- Personality: {c['personality']}",
        f"- Animation: {', '.join(c['animation_tendencies'])}", "",
    ]
(ROOT / "generated" / "character-registry.md").write_text("\n".join(lines), encoding="utf-8")
print(ROOT / "generated" / "character-registry.md")
