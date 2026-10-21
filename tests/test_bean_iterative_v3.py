"""Independent regression for combinatorial 32-evaluation model-free logic."""
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
    raise unittest.SkipTest("optional BEAN Core checkout needed: "+str(exc))
FILE=Path(__file__).resolve().parents[1]/"experiments/bean_iterative_search/engine_v3.py"
spec=importlib.util.spec_from_file_location("axiom_bean_v3_test",FILE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
class ReasoningTests(unittest.TestCase):
    def case(self):
        for episode in range(25):
            regime,jobs=m.v1.lab.workload(90,episode)
            if m.valid_case(jobs):
                return regime,jobs
        self.fail("fixture did not contain all three families")

    def test_18_novel_compositions_and_strict_32_budget(self):
        regime,jobs=self.case()
        seqs=m.structured_sequences(jobs)
        self.assertEqual(len(seqs),18)
        for name,sequence in seqs:
            self.assertEqual(set(sequence),set(range(8)))
            self.assertGreater(m.v1.objective(jobs,regime,sequence),0)
        for op in m.v1.OPERATORS:
            p=m.run_search(jobs,regime,op,seed=910)
            self.assertEqual(len(p["trace"]),32)
            self.assertLessEqual(p["cost"],p["initial_cost"])
            self.assertLessEqual(p["cost"],p["structured_cost"])
            self.assertEqual(p["cost"],m.v1.objective(jobs,regime,p["best_sequence"]))

    def test_real_q_updates_and_sealed_holdout_recovery(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/"trial"
            r=m.run_seed(folder,1093,train_cases=55,holdout=17)
            self.assertEqual(r["Q_updates"],55)
            self.assertEqual(r["holdout_cases"],17)
            self.assertEqual(r["candidate_budget"],32)
            source=json.loads(gzip.decompress(
                (folder/"complete_trials.json.gz").read_bytes()))
            self.assertEqual(len(source["train"]),55)
            self.assertEqual(len(source["heldout"]),17)
            for e in source["heldout"]:
                for result in e["results"].values():
                    self.assertEqual(len(result["trace"]),32)
            ledger=PortfolioLedger(folder/"q.sqlite")
            try:
                self.assertEqual(ledger.verify()["rewarded_events"],55)
                self.assertIsNotNone(ledger.event(m.APP,"v3_000000"))
                self.assertIsNone(ledger.event(m.APP,"v3_000055"))
            finally:
                ledger.close()

    def test_distinct_cold_seeds(self):
        with tempfile.TemporaryDirectory() as temp:
            r=m.run_all(Path(temp),seeds=(11,29),train_cases=20,heldout=11)
            self.assertEqual(r["actual_Q_updates"],40)
            self.assertEqual(r["model_calls"],0)
            self.assertEqual(r["holdout_cases"],22)
            self.assertNotEqual(r["seeds"][0]["holdout_sha256"],
                                r["seeds"][1]["holdout_sha256"])
if __name__=="__main__":
    unittest.main()
