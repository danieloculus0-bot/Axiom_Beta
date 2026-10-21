"""No-LLM exact-replay tests for BEAN's iterative candidate schedule learner."""
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
    raise unittest.SkipTest("Optional BEAN Core checkout needed: "+str(exc))

FILE=Path(__file__).resolve().parents[1]/"experiments/bean_iterative_search/engine.py"
spec=importlib.util.spec_from_file_location("axiom_bean_iterative_test",FILE)
eng=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=eng
spec.loader.exec_module(eng)


class IterativeSchedulingTests(unittest.TestCase):
    def test_schedule_score_matches_existing_independent_evaluator(self):
        for seed in (11,29,41):
            regime,jobs=eng.lab.workload(seed,2)
            for rule,seq,cost in eng.seeds(jobs,regime):
                self.assertEqual(cost,eng.objective(jobs,regime,seq))
                self.assertEqual(cost,eng.lab.dispatch(jobs,rule,regime=regime)["cost"])

    def test_seven_mutations_retain_exact_job_permutation(self):
        for seed in (11,29,41):
            regime,jobs=eng.lab.workload(seed,2)
            original=eng.seeds(jobs,regime)[0][1]
            import random
            for op in eng.OPERATORS:
                for x in range(15):
                    mutated=eng.candidate(original,jobs,regime,op,random.Random(x))
                    self.assertEqual(len(mutated),len(jobs))
                    self.assertEqual(set(mutated),set(original))
                    self.assertGreater(eng.objective(jobs,regime,mutated),0)

    def test_equal_budget_and_no_increasing_best_cost(self):
        regime,jobs=eng.lab.workload(1093,5)
        for op in eng.OPERATORS:
            result=eng.evaluate_policy(jobs,regime,op,case_seed=28,budget=32)
            self.assertEqual(len(result["trace"]),32)
            self.assertEqual(result["candidate_evaluations"],32)
            self.assertLessEqual(result["cost"],result["best_fixed_cost"])
            self.assertEqual(result["cost"],eng.objective(
                jobs,regime,result["sequence"]))
            self.assertEqual(result["trace"][-1]["trial"],31)

    def test_real_beAN_q_updates_audited_and_holdout_does_not_train(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/"trial"
            report=eng.train_and_evaluate(root,1093,episodes=80,
                                          holdout_cases=25,budget=20)
            self.assertEqual(report["Q_updates"],80)
            self.assertEqual(report["ledger"]["rewarded_events"],80)
            self.assertEqual(report["frozen_holdout"]["cases"],25)
            self.assertEqual(report["evaluation_budget_per_case"],20)
            self.assertEqual(report["LLM_calls"],0)
            restored=gzip.decompress((root/"all_exact_trials.json.gz").read_bytes())
            content=json.loads(restored)
            self.assertEqual(len(content["train_cases"]),80)
            self.assertEqual(len(content["holdout_cases"]),25)
            self.assertEqual(sum(x["type"]=="observed"
                                 for x in content["feedback_events"]),80)
            for row in content["holdout_cases"]:
                for k in ("BEAN_Q","feedback_reflection",
                          "random_untrained","blend_untrained"):
                    self.assertEqual(len(row["results"][k]["trace"]),20)
            ledger=PortfolioLedger(root/"bean.sqlite")
            try:
                self.assertEqual(ledger.verify()["rewarded_events"],80)
                self.assertEqual(ledger.event(eng.APP,"q_000000")["reward"],
                                 round(content["train_cases"][0]["q_reward"],10))
                self.assertIsNone(ledger.event(eng.APP,"q_000080"))
            finally:
                ledger.close()

    def test_three_seeds_do_not_reuse_holdout_or_fake_gepa(self):
        with tempfile.TemporaryDirectory() as temp:
            out=eng.run_all(Path(temp),seeds_in=(11,29),
                            episodes=35,cases=12,budget=12)
            self.assertEqual(out["Q_updates_total"],70)
            self.assertEqual(out["LLM_calls"],0)
            self.assertEqual(out["official_GEPA_runs"],0)
            self.assertEqual(out["OpenHands_runs"],0)
            self.assertNotEqual(
                out["seed_results"][0]["holdout"]["holdout_sha256"],
                out["seed_results"][1]["holdout"]["holdout_sha256"])

if __name__=="__main__":
    unittest.main()
