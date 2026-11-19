"""Regression tests for branched ChatGPT `mapping` data (edited / regenerated turns).

Playwright is stubbed, so these run offline through the public
``extract_messages_with_playwright`` entry point with synthetic fixtures.
"""

import contextlib
import io
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _FakePage:
    def __init__(self, result):
        self._result = result

    def add_init_script(self, script):
        pass

    def goto(self, url, **kwargs):
        pass

    def wait_for_timeout(self, ms):
        pass

    def wait_for_selector(self, selector, **kwargs):
        pass

    def evaluate(self, script):
        # Only the big extraction script mentions __NEXT_DATA__.
        if "__NEXT_DATA__" in script:
            return self._result
        return 0


class _FakeBrowser:
    def __init__(self, result):
        self._result = result
        self.closed = False

    def new_context(self, **kwargs):
        return self

    def new_page(self):
        return _FakePage(self._result)

    def close(self):
        self.closed = True


class _FakePlaywright:
    result = None
    last_browser = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def chromium(self):
        return self

    def launch(self, **kwargs):
        _FakePlaywright.last_browser = _FakeBrowser(_FakePlaywright.result)
        return _FakePlaywright.last_browser


def _install_playwright_stub():
    pkg = types.ModuleType("playwright")
    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = lambda: _FakePlaywright()
    pkg.sync_api = sync_api
    sys.modules["playwright"] = pkg
    sys.modules["playwright.sync_api"] = sync_api


_install_playwright_stub()
import chatgpt_to_markdown as ctm  # noqa: E402


def node(node_id, parent, role=None, text=None, create_time=0, **extra):
    """Build one mapping node. role=None means a node with no message."""
    message = None
    if role is not None:
        message = {
            "author": {"role": role},
            "content": {"parts": [text] if text is not None else []},
            "create_time": create_time,
        }
    data = {"id": node_id, "parent": parent, "message": message, "children": []}
    data.update(extra)
    return node_id, data


def extract(result):
    _FakePlaywright.result = result
    with contextlib.redirect_stdout(io.StringIO()):
        messages = ctm.extract_messages_with_playwright(
            "https://chatgpt.com/share/synthetic", ctm.Config()
        )
    assert _FakePlaywright.last_browser.closed
    return [(m.speaker, m.content) for m in messages]


def branched_mapping():
    """root -> sys -> q1 -> a1(abandoned) / a1b(regenerated) -> q2(abandoned) / q2b(edited) -> a2b"""
    return dict(
        [
            node("root", None),
            node("sys", "root", "system", "", 1),
            node("q1", "sys", "user", "Question one", 10),
            node("a1", "q1", "assistant", "Abandoned answer", 11),
            node("a1b", "q1", "assistant", "Regenerated answer", 12),
            node("q2", "a1", "user", "Abandoned follow-up", 13),
            node("a2", "q2", "assistant", "Abandoned follow-up answer", 14),
            node("q2b", "a1b", "user", "Edited follow-up", 15),
            node("a2b", "q2b", "assistant", "Final answer", 16),
        ]
    )


ACTIVE = [
    ("User", "Question one"),
    ("ChatGPT", "Regenerated answer"),
    ("User", "Edited follow-up"),
    ("ChatGPT", "Final answer"),
]


class ActiveLineageTests(unittest.TestCase):
    def test_only_active_branch_is_exported(self):
        result = {"mapping": branched_mapping(), "current_node": "a2b"}
        self.assertEqual(extract(result), ACTIVE)

    def test_current_node_may_be_mid_tree(self):
        result = {"mapping": branched_mapping(), "current_node": "a1"}
        self.assertEqual(
            extract(result),
            [("User", "Question one"), ("ChatGPT", "Abandoned answer")],
        )

    def test_mapping_order_does_not_matter(self):
        mapping = dict(reversed(list(branched_mapping().items())))
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), ACTIVE)

    def test_timestamps_do_not_reorder_lineage(self):
        mapping = branched_mapping()
        mapping["q1"]["message"]["create_time"] = 999
        mapping["a1b"]["message"]["create_time"] = None
        mapping["q2b"]["message"]["create_time"] = 1
        del mapping["a2b"]["message"]["create_time"]
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), ACTIVE)

    def test_follows_parents_through_non_exportable_nodes(self):
        mapping = dict(
            [
                node("root", None),
                node("q1", "root", "user", "Hello", 1),
                node("tool", "q1", "tool", "tool output", 2),
                node("empty", "tool", "assistant", "", 3),
                node("blank", "empty"),
                node("a1", "blank", "assistant", "Hi there", 4),
                node("other", "q1", "assistant", "Abandoned", 5),
                node("tail", "a1"),
            ]
        )
        self.assertEqual(
            extract({"mapping": mapping, "current_node": "tail"}),
            [("User", "Hello"), ("ChatGPT", "Hi there")],
        )

    def test_active_lineage_skips_message_without_role(self):
        mapping = branched_mapping()
        del mapping["a1b"]["message"]["author"]["role"]
        self.assertEqual(
            extract({"mapping": mapping, "current_node": "a2b"}),
            [
                ("User", "Question one"),
                ("User", "Edited follow-up"),
                ("ChatGPT", "Final answer"),
            ],
        )

    def test_root_without_parent_key(self):
        mapping = branched_mapping()
        del mapping["root"]["parent"]
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), ACTIVE)


class FallbackTests(unittest.TestCase):
    ALL = [
        ("User", "Question one"),
        ("ChatGPT", "Abandoned answer"),
        ("ChatGPT", "Regenerated answer"),
        ("User", "Abandoned follow-up"),
        ("ChatGPT", "Abandoned follow-up answer"),
        ("User", "Edited follow-up"),
        ("ChatGPT", "Final answer"),
    ]

    def test_missing_current_node_uses_chronological_fallback(self):
        mapping = dict(reversed(list(branched_mapping().items())))
        self.assertEqual(extract({"mapping": mapping}), self.ALL)

    def test_legacy_fallback_preserves_message_without_role(self):
        mapping = branched_mapping()
        del mapping["a1b"]["message"]["author"]["role"]
        self.assertEqual(extract({"mapping": mapping}), self.ALL)

    def test_null_current_node_uses_fallback(self):
        result = {"mapping": branched_mapping(), "current_node": None}
        self.assertEqual(extract(result), self.ALL)

    def test_current_node_not_in_mapping_uses_fallback(self):
        result = {"mapping": branched_mapping(), "current_node": "nope"}
        self.assertEqual(extract(result), self.ALL)

    def test_missing_parent_node_uses_fallback(self):
        mapping = branched_mapping()
        mapping["q1"]["parent"] = "gone"
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), self.ALL)

    def test_cycle_uses_fallback(self):
        mapping = branched_mapping()
        mapping["root"]["parent"] = "a2b"
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), self.ALL)

    def test_self_cycle_uses_fallback(self):
        mapping = branched_mapping()
        mapping["a2b"]["parent"] = "a2b"
        self.assertEqual(extract({"mapping": mapping, "current_node": "a2b"}), self.ALL)

    def test_unusable_timestamps_are_zero_and_ties_keep_mapping_order(self):
        mapping = dict(
            [
                node("late", None, "assistant", "late", 5),
                node("none", "late", "user", "null time", None),
                node("text", "none", "assistant", "string time", "yesterday"),
                node("nan", "text", "user", "nan time", float("nan")),
                node("zero", "nan", "assistant", "zero time", 0),
                node("absent", "zero", "user", "absent time", 0),
                node("neg", "absent", "assistant", "negative time", -1),
                node("early", "neg", "user", "early", 2.5),
            ]
        )
        del mapping["absent"]["message"]["create_time"]
        self.assertEqual(
            extract({"mapping": mapping}),
            [
                ("ChatGPT", "negative time"),
                ("User", "null time"),
                ("ChatGPT", "string time"),
                ("User", "nan time"),
                ("ChatGPT", "zero time"),
                ("User", "absent time"),
                ("User", "early"),
                ("ChatGPT", "late"),
            ],
        )


class OtherRoutesTests(unittest.TestCase):
    def test_dom_route_unchanged(self):
        result = {
            "dom_elements": [
                {"role": "user", "text": "Hi"},
                {"text": "Hello"},
                {"role": "assistant", "text": "Login"},
            ],
            "current_node": "ignored",
        }
        self.assertEqual(extract(result), [("User", "Hi"), ("ChatGPT", "Hello")])

    def test_linear_conversation_route_unchanged(self):
        result = {
            "linear_conversation": [
                {"id": "root"},
                {"message": {"author": {"role": "user"}, "content": {"parts": ["Q"]}}},
                {"message": {"author": {"role": "assistant"}, "content": {"parts": ["A", "x"]}}},
                {"message": {"author": {"role": "assistant"}, "content": {"parts": [""]}}},
            ],
            "current_node": "ignored",
        }
        self.assertEqual(extract(result), [("User", "Q"), ("ChatGPT", "A")])

    def test_no_data_returns_empty(self):
        self.assertEqual(extract(None), [])


if __name__ == "__main__":
    unittest.main()
