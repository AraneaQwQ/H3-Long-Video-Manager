"""H3 Long Video Manager — V3 Node Schema Tests (needs ComfyUI's comfy_api)."""

import importlib.util
import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

sys.path.insert(0, REPO)


def _comfy_roots():
    env_root = os.environ.get("COMFYUI_ROOT")
    if env_root:
        yield env_root
    custom_nodes = os.path.dirname(REPO)
    if os.path.basename(custom_nodes) == "custom_nodes":
        yield os.path.dirname(custom_nodes)


def _load_nodes():
    last_error = None
    for root in _comfy_roots():
        if root not in sys.path:
            sys.path.insert(0, root)
        try:
            spec = importlib.util.spec_from_file_location(
                "h3lvm",
                os.path.join(REPO, "__init__.py"),
                submodule_search_locations=[REPO],
            )
            package = importlib.util.module_from_spec(spec)
            sys.modules["h3lvm"] = package
            spec.loader.exec_module(package)
            return importlib.import_module("h3lvm.comfyui.nodes"), None
        except Exception as exc:
            last_error = exc
    return None, last_error


NODES, LOAD_ERROR = _load_nodes()


def _outputs(node_name):
    node_cls = next(cls for cls in NODES.NODE_LIST if cls.__name__ == node_name)
    return [out.display_name for out in node_cls.define_schema().outputs]


def _input_ids(node_name):
    node_cls = next(cls for cls in NODES.NODE_LIST if cls.__name__ == node_name)
    return [inp.id for inp in node_cls.define_schema().inputs]


# LGraphNode.configure() restores widget values by position, so a new field may
# only ever be appended here; final_align stays declared even though it is
# ignored, for the same reason.
MANAGER_INPUTS = [
    "video", "fps", "segment_duration", "motion_context_frames", "segment_id",
    "audio", "scale_percent", "align_to_h3_grid", "project_name", "save_enabled",
    "save_preview_mp4", "final_align", "person_crop", "person_crop_expand_percent",
    "save_dtype",
]


@unittest.skipIf(NODES is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestNodeSchema(unittest.TestCase):
    def test_manager_input_order(self):
        self.assertEqual(_input_ids("H3LongVideoManager"), MANAGER_INPUTS)

    def test_picker_input_order(self):
        self.assertEqual(_input_ids("H3SegmentPicker"), ["project_name", "segment_id"])

    def test_picker_outputs(self):
        # segment_id is appended last so existing 3-output links stay valid.
        self.assertEqual(
            _outputs("H3SegmentPicker"),
            ["IMAGE", "AUDIO", "frame_count", "segment_id"],
        )

    def test_manager_outputs(self):
        self.assertEqual(
            _outputs("H3LongVideoManager"),
            ["IMAGE", "AUDIO", "frame_count", "total_segments"],
        )


# Smart Split is a new node, so its order is free to be the clean one: no
# deprecated final_align, no Manager-only fields it must not expose.
SMART_INPUTS = [
    "video", "fps", "detection_sensitivity", "motion_context_frames", "segment_id",
    "audio", "scale_percent", "project_name", "save_enabled", "save_preview_mp4",
    "save_dtype",
]


@unittest.skipIf(NODES is None, f"comfy_api unavailable: {LOAD_ERROR}")
class TestSmartSplitSchema(unittest.TestCase):
    def test_registered(self):
        self.assertIn("H3SmartSplit", [cls.__name__ for cls in NODES.NODE_LIST])

    def test_input_order(self):
        self.assertEqual(_input_ids("H3SmartSplit"), SMART_INPUTS)

    def test_outputs_match_the_manager(self):
        # The Picker must be able to read either producer unchanged.
        self.assertEqual(
            _outputs("H3SmartSplit"),
            _outputs("H3LongVideoManager"),
        )

    def test_no_fixed_duration_or_h3_alignment(self):
        """Planning doc sections 34 and 8: smart split has no fixed slice length."""
        forbidden = {"segment_duration", "align_to_h3_grid", "final_align",
                     "person_crop", "person_crop_expand_percent"}
        self.assertEqual(forbidden.intersection(set(_input_ids("H3SmartSplit"))), set())

    def test_motion_context_menu_and_default(self):
        schema = next(cls for cls in NODES.NODE_LIST if cls.__name__ == "H3SmartSplit").define_schema()
        mc = next(inp for inp in schema.inputs if inp.id == "motion_context_frames")
        self.assertEqual(list(mc.options), ["0", "5", "22", "39", "56"])
        self.assertEqual(mc.default, "0")

    def test_saving_bypasses_the_cache(self):
        self.assertNotEqual(NODES.H3SmartSplit.fingerprint_inputs(save_enabled=True), False)
        self.assertFalse(NODES.H3SmartSplit.fingerprint_inputs(save_enabled=False))


if __name__ == "__main__":
    unittest.main()
