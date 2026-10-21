"""Real Axiom to separate BEAN portfolio Core integration test.

Only synthetic anonymized metadata and expressly chosen rewards are sent.
"""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

# The isolated adapter is stdlib-only; importing all of superforge would also
# load Flask and the native ERP runtime, irrelevant to this executable contract.
import importlib.util
_ADAPTER=Path(__file__).resolve().parents[1]/"superforge/integrations/bean_portfolio.py"
_spec=importlib.util.spec_from_file_location("bean_portfolio_isolated",_ADAPTER)
_mod=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
BeanPortfolioClient=_mod.BeanPortfolioClient


class BeanPortfolioIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        core = os.environ.get("BEAN_CORE_DIR")
        if not core:
            self.skipTest("Separate BEAN research checkout required")
        self.client = BeanPortfolioClient(core,Path(self.tmp.name)/"bean.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def test_event_context_and_rewarded_replay(self):
        source = SimpleNamespace(
            source_module="quality",event_id="evt_test_001",
            event_type="quality.created",
            payload={"employee":"SHOULD_NOT_LEAVE_AXIOM","secret":"DO_NOT_SEND"},
            actor="PRIVATE_PERSON")
        saved = self.client.observe_domain_event(source)
        self.assertTrue(saved["new"])
        self.assertFalse(self.client.observe_domain_event(source)["new"])
        context = self.client.context(module="quality",query="created")
        self.assertEqual(context["total_events"],1)
        self.assertNotIn("PRIVATE_PERSON",str(context))
        self.assertNotIn("SHOULD_NOT_LEAVE_AXIOM",str(context))
        self.assertEqual(self.client.verify()["q_entries"],0)
        result = self.client.observe(module="quality",event_id="eval_synthetic_001",
            state="quality/corrective_action",action="investigate",
            reward=1.5,next_state="quality/closed",done=False,
            evidence_ref="test://independent-fixture-1",kind="synthetic",
            revision="integration-test")
        self.assertTrue(result["new"])
        self.assertEqual(self.client.verify()["q_entries"],1)
        self.assertEqual(self.client.verify()["events"],2)
        self.assertFalse(self.client.observe(module="quality",event_id="eval_synthetic_001",
            state="quality/corrective_action",action="investigate",
            reward=1.5,next_state="quality/closed",done=False,
            evidence_ref="test://independent-fixture-1",kind="synthetic",
            revision="integration-test")["new"])
        self.assertEqual(self.client.verify()["events"],2)
        with self.assertRaises(ValueError):
            self.client.observe(module="quality bad",event_id="id",
                state="a",evidence_ref="test://x")


if __name__ == "__main__":
    unittest.main()
