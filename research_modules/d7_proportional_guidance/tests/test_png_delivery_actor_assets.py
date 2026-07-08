from __future__ import annotations

import ast
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = MODULE_ROOT / "png_guidance_delivery" / "examples"
ACTOR_ASSET_EXAMPLES = (
    "run_airsim_truth_png.py",
    "run_airsim_gimbal_vision_png.py",
    "run_airsim_strapdown_vision_png.py",
)


def _intruder_actor_asset_default(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "add_argument":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        if node.args[0].value != "--intruder-actor-asset":
            continue
        for keyword in node.keywords:
            if keyword.arg == "default" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
    raise AssertionError(f"{path} does not define --intruder-actor-asset default")


def test_png_delivery_actor_asset_defaults_to_quadrotor1() -> None:
    defaults = {
        filename: _intruder_actor_asset_default(EXAMPLES_DIR / filename)
        for filename in ACTOR_ASSET_EXAMPLES
    }

    assert defaults == {
        "run_airsim_truth_png.py": "Quadrotor1",
        "run_airsim_gimbal_vision_png.py": "Quadrotor1",
        "run_airsim_strapdown_vision_png.py": "Quadrotor1",
    }
