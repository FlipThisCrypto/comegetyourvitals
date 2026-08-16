from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
from long_scene_provenance import (  # noqa: E402
    attempt_number,
    build_spec,
    diversified_seed,
    spec_matches,
    write_spec,
)


class LongSceneProvenanceTests(unittest.TestCase):
    def spec(self, root: Path, **changes):
        start = root / "start.png"
        end = root / "end.png"
        if not start.exists():
            start.write_bytes(b"start")
        if not end.exists():
            end.write_bytes(b"end")
        values = dict(
            scene_id="scene", segment=1, attempt=1, prompt="action", negative_prompt="bad anatomy",
            start_frame=start, end_frame=end, seed=123, model="model", provider_settings={"steps": 24},
            width=848, height=480, duration_seconds=10, native_fps=8, delivery_fps=60,
        )
        values.update(changes)
        return build_spec(**values)

    def test_unchanged_spec_resumes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            spec = self.spec(root)
            path = root / "generation-spec.json"
            write_spec(path, spec)
            self.assertTrue(spec_matches(path, spec))

    def test_prompt_or_anchor_change_invalidates_cache(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            original = self.spec(root)
            path = root / "generation-spec.json"
            write_spec(path, original)
            changed = dict(original, prompt="different action")
            self.assertFalse(spec_matches(path, changed))
            (root / "start.png").write_bytes(b"changed start")
            changed_anchor = self.spec(root)
            self.assertFalse(spec_matches(path, changed_anchor))

    def test_retry_changes_attempt_and_seed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(attempt_number(root), 1)
            (root / "rejected-attempts" / "attempt-001").mkdir(parents=True)
            self.assertEqual(attempt_number(root), 2)
            self.assertNotEqual(diversified_seed("scene", 0, 1), diversified_seed("scene", 0, 2))


if __name__ == "__main__":
    unittest.main()
