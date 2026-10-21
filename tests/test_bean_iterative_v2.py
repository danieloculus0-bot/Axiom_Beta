"""BEAN v2 independent holdout, real per-block Q state and tactic switch tests."""
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
try:
    from bean.optimization.portfolio_ledger import PortfolioLedger
except ModuleNotFoundError as exc:
    raise unittest.SkipTest("optional separate BEAN Core required: "+str(exc))
FILE=Path(__file__).resolve().parents[1]/"experiments/bean_iterative_search/engine_v2.py"
spec=importlib.util.spec_from_file_location("axiom_bean_v2_test",FILE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)

class BeanIterationV2Tests(unittest.TestCase):
    def test_32_measured_proposals_and_independent_score(self):
        regime,jobs=m.v1.lab.workload(98,12)
        p=m.search(jobs,regime,case_seed=3392,explore=1,budget=32)
        self.assertEqual(p["evaluations"],32)
        self.assertEqual(len(p["trace"]),32)
        self.assertEqual(len(p["blocks"]),7)
        self.assertLessEqual(p["cost"],p["initial"])
        self.assertEqual(p["cost"],m.v1.objective(jobs,regime,p["sequence"]))
        self.assertEqual(set(p["sequence"]),set(range(8)))

    def test_true_q_updates_and_holdout_never_trains(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/"run"
            r=m.train_and_compare(folder,1093,episodes=60,holdout=17,budget=32)
            self.assertEqual(r["q_updates"],420)
            self.assertEqual(r["Q_ledger"]["rewarded_events"],420)
            self.assertEqual(r["language_model_calls"],0)
            content=json.loads(gzip.decompress(
                (folder/"exact_training_and_holdout.json.gz").read_bytes()))
            self.assertEqual(len(content["train"]),60)
            self.assertEqual(len(content["holdout"]),17)
            for item in content["holdout"]:
                for key,result in item["results"].items():
                    self.assertEqual(len(result["trace"]),32,
                                     "unequal evaluation budgets: "+key)
            db=PortfolioLedger(folder/"bean-blocks.sqlite")
            try:
                self.assertEqual(db.verify()["rewarded_events"],420)
                self.assertIsNotNone(db.event(m.APP,"v2_000000_00"))
                self.assertIsNone(db.event(m.APP,"v2_000060_00"))
            finally:db.close()

    def test_multiple_seeds_unseen_and_zero_official_agents(self):
        with tempfile.TemporaryDirectory() as temp:
            r=m.run(Path(temp),seeds=(19,29),episodes=20,holdout=11)
            self.assertEqual(r["total_Q_learning_updates"],280)
            self.assertEqual(r["total_training_cases"],40)
            self.assertEqual(r["total_frozen_holdout_cases"],22)
            self.assertEqual(r["model_calls"],0)
            self.assertNotEqual(r["each_seed"][0]["holdout_sha256"],
                                r["each_seed"][1]["holdout_sha256"])
if __name__=="__main__":
    unittest.main()
