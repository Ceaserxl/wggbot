from __future__ import annotations

from modules.stablediffusion import StableDiffusionCog


def test_workflow_path_and_prompt_patch_are_valid() -> None:
    graph, save_node = StableDiffusionCog._workflow("a test prompt")
    assert graph["56"]["inputs"]["value"] == "a test prompt"
    assert 1 <= graph["155"]["inputs"]["value"] <= 2_147_483_647
    assert graph[save_node]["class_type"] == "SaveImage"
