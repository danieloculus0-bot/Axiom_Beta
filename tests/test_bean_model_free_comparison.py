"""Evidence-grounded, LLM-free head-to-head. Official GEPA/OpenHands not run."""
from __future__ import annotations
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

try:
    from bean.optimization.portfolio_ledger import PortfolioLedger
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("Pinned independent BEAN Core required: "+str(exc))

FILE=Path(__file__).resolve().parents[1]/"experiments/bean_model_free_comparison/benchmark.py"
spec=importlib.util.spec_from_file_location("axiom_bean_competition",FILE)
mod=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=mod
spec.loader.exec_module(mod)


class ModelFreeComparisonTests(unittest.TestCase):
    def test_same_sealed_case_and_auditable_feedback(self):
        with tempfile.TemporaryDirectory() as temp:
            result=mod.one_seed(Path(temp)/"one",seed=1093,episodes=60,
                                holdout_cases=30)
            self.assertEqual(result["BEAN_real_Q_updates"],60)
            self.assertEqual(result["holdout"]["mutation_decisions"]["fifo"]+
                             sum(result["holdout"]["mutation_decisions"][x]
                                 for x in mod.lab.ACTIONS if x!="fifo"),30)
            self.assertFalse(result["engines"]["official_GEPA_executed"])
            self.assertFalse(result["engines"]["OpenHands_executed"])
            self.assertEqual(result["engines"]["language_model_invocations"],0)
            self.assertTrue(result["archive"]["exact_recovery"])
            payload=json.loads(gzip.decompress(
                (Path(temp)/"one"/"all_training_events.json.gz").read_bytes()))
            self.assertEqual(len(payload["bean_trials"]),60)
            events=payload["feedback_events"]
            self.assertEqual(sum(e["type"]=="observed_case" for e in events),60)
            previous="GENESIS"
            for event in events:
                self.assertEqual(event["previous_hash"],previous)
                unfixed={k:v for k,v in event.items()
                         if k not in ("chain_hash","previous_hash")}
                self.assertEqual(event["chain_hash"],mod.sha(
                    [previous,{**unfixed,"previous_hash":previous}]))
                previous=event["chain_hash"]
            self.assertEqual(previous,result["feedback_ledger_tip"])
            learner=PortfolioLedger(Path(temp)/"one"/"bean.sqlite")
            try:
                self.assertEqual(learner.verify()["rewarded_events"],60)
            finally:
                learner.close()

    def test_different_seeds_do_not_fake_framework_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            x=mod.run(Path(temp),seeds=(11,29),episodes=30,holdout_cases=20)
            self.assertEqual(x["total_BEAN_Q_updates"],60)
            self.assertEqual(x["total_feedback_training_cases"],60)
            self.assertEqual(x["actual_gepa_runs"],0)
            self.assertEqual(x["actual_openhands_runs"],0)
            self.assertEqual(x["language_model_calls"],0)
            self.assertEqual(len(x["per_seed"]),2)
            self.assertNotEqual(x["per_seed"][0]["holdout"]["fixture_sha256"],
                                x["per_seed"][1]["holdout"]["fixture_sha256"])

    def test_reject_bad_budgets(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                mod.one_seed(temp,1093,episodes=0)
            with self.assertRaises(ValueError):
                mod.one_seed(temp,1093,episodes=3001)
            with self.assertRaises(ValueError):
                mod.one_seed(temp,1093,holdout_cases=2)


if __name__=="__main__":
    unittest.main()
