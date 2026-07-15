from __future__ import annotations

import inspect
import unittest
from pathlib import Path
from types import SimpleNamespace

from tests._bootstrap import install_optional_dependency_stubs

install_optional_dependency_stubs()

import nightly_discovery
from admin_panel_runtime_v5 import TelegramPanelRuntimeV5
from admin_panel_runtime_v14 import TelegramPanelRuntimeV14
from admin_panel_runtime_v17 import TelegramPanelRuntimeV17
from admin_panel_runtime_v38 import TelegramPanelRuntimeV38


ROOT = Path(__file__).resolve().parents[1]


class NightlyIdlePolicyTests(unittest.TestCase):
    def test_completion_notice_requires_a_real_manual_scan(self) -> None:
        self.assertFalse(
            nightly_discovery.should_notify_completion(
                manual_run=True, catalog_size_at_start=0
            )
        )
        self.assertFalse(
            nightly_discovery.should_notify_completion(
                manual_run=False, catalog_size_at_start=3
            )
        )
        self.assertTrue(
            nightly_discovery.should_notify_completion(
                manual_run=True, catalog_size_at_start=3
            )
        )

    def test_candidate_changes_do_not_dispatch_a_nightly_scan(self) -> None:
        for method in (
            TelegramPanelRuntimeV5.set_candidate_mode,
            TelegramPanelRuntimeV5.restore_candidate,
            TelegramPanelRuntimeV14.bulk_set_intelligence_mode,
            TelegramPanelRuntimeV17.decide_source_request,
        ):
            self.assertNotIn("nightly-discovery.yml", inspect.getsource(method))

    def test_catalog_change_does_not_trigger_nightly_workflow(self) -> None:
        workflow = (ROOT / ".github/workflows/nightly-discovery.yml").read_text(
            encoding="utf-8"
        )
        push_paths = workflow.split("workflow_dispatch:", 1)[0]
        self.assertNotIn('"source_catalog.txt"', push_paths)
        self.assertNotIn('"public_sources.txt"', push_paths)

    def test_empty_nightly_list_is_shown_as_idle_without_start_button(self) -> None:
        panel = TelegramPanelRuntimeV38()
        captured: list[tuple[str, dict]] = []
        panel.current_user_id = "1"
        panel.current_chat_id = "1"
        panel.current_role = "owner"
        panel.navigation = {"1": ["menu", "discovery"]}
        panel.is_admin = lambda: True  # type: ignore[method-assign]
        panel.snapshot = lambda force=False: SimpleNamespace(  # type: ignore[method-assign]
            state={},
            stats={"sources": {}, "daily": {}},
            health={"sources": {}},
            discovery={"sources": {}},
            fast=["mechanogun"],
            nightly=[],
        )
        panel.candidate_rows = lambda: []  # type: ignore[method-assign]
        panel.workflow_run = lambda value: {  # type: ignore[method-assign]
            "status": "completed",
            "conclusion": "success",
        }
        panel.send = lambda text, **kwargs: captured.append((text, kwargs)) or {}  # type: ignore[method-assign]

        panel.show_discovery()

        text, kwargs = captured[-1]
        self.assertIn("не требуется — ночной список пуст", text)
        self.assertNotIn("control:nightly", str(kwargs.get("reply_markup")))
        self.assertIn("page:discovery", str(kwargs.get("reply_markup")))


if __name__ == "__main__":
    unittest.main()
