"""Tests real BEAN ledger with synthetic Axiom scheduling, no live ERP I/O."""
from __future__ import annotations
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

LAB=Path(__file__).resolve().parents[1]/"superforge/integrations/bean_optimization_lab.py"
_spec=importlib.util.spec_from_file_location("axiom_bean_optimization_lab",LAB)
_mod=importlib.util.module_from_spec(_spec)
import sys
sys.modules[_spec.name]=_mod
_spec.loader.exec_module(_mod)


class BEANAxiomOptimizerTests(unittest.TestCase):
    def test_deterministic_simulation_and_well_defined_cost(self):
        regime,jobs=_mod.workload(112,44)
        again=_mod.workload(112,44)
        self.assertEqual((regime,jobs),again)
        self.assertEqual(len(jobs),8)
        for strategy in _mod.ACTIONS:
            result=_mod.dispatch(jobs,strategy,regime=regime)
            self.assertEqual(set(result["sequence"]),set(range(8)))
            self.assertGreater(result["cost"],0)
            self.assertGreaterEqual(result["tardiness"],0)
        reward,competing=_mod.score_case(regime,jobs,"fifo")
        self.assertEqual(reward,0.0)
        self.assertEqual(set(competing),set(_mod.ACTIONS))

    def test_q_learning_updates_and_full_evidence_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"research.sqlite"
            report,trials=_mod.run_training(
                file,episodes=100,train_seed=1093,
                validate_seed=55001,holdout_seed=99001,test_cases=30)
            self.assertEqual(report["training_episodes"],100)
            self.assertEqual(report["actual_q_updates"],100)
            self.assertEqual(len(trials),100)
            self.assertEqual(report["ledger_verify"]["events"],100)
            self.assertEqual(report["portfolio_scoreboard"]["apps_total"],1)
            self.assertEqual(len(report["validation_checkpoints"]),1)
            self.assertEqual(report["validation_checkpoints"][-1]["at_episode"],100)
            self.assertEqual(report["independent_holdout"]["cases"],30)
            self.assertEqual(sum(report["independent_holdout"]["decision_counts"].values()),30)
            # Proof that the independent BEAN storage was actually used:
            p=_mod.PortfolioLedger(file)
            try:
                self.assertEqual(p.verify()["rewarded_events"],100)
                original=p.event(_mod.APP,"episode_000000")
                self.assertEqual(original["reward"],trials[0]["reward"])
                self.assertEqual(original["evidence_ref"],
                                 "synthetic://axiom/scheduling/"+
                                 _mod.sha(_mod.canonical({
                                     k:v for k,v in trials[0].items()
                                     if k!="event_receipt"}))[:32])
            finally:
                p.close()
            with self.assertRaisesRegex(ValueError,"empty isolated"):
                _mod.run_training(file,episodes=5,test_cases=20)

    def test_read_only_holdout_does_not_train(self):
        with tempfile.TemporaryDirectory() as temp:
            store=_mod.PortfolioLedger(Path(temp)/"ledger.sqlite")
            try:
                prior=store.verify()
                result=_mod.evaluate(store,99001,60)
                self.assertEqual(result["cases"],60)
                self.assertEqual(store.verify(),prior)
                self.assertEqual(sum(result["decision_counts"].values()),60)
                self.assertTrue(result["mean_cost"]["per_case_oracle"] <=
                                result["mean_cost"]["bean_q"])
                self.assertTrue(result["mean_cost"]["per_case_oracle"] <=
                                result["mean_cost"]["fifo"])
            finally:
                store.close()

    def test_invalid_conditions_prevent_fabricated_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Path(temp)/"bad.sqlite"
            with self.assertRaisesRegex(ValueError,"differ"):
                _mod.run_training(store,episodes=5,train_seed=1,
                                  validate_seed=1,holdout_seed=3)
            with self.assertRaisesRegex(ValueError,"episodes"):
                _mod.run_training(store,episodes=3001)

    def test_real_q_receipts_detect_db_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/"verified.sqlite"
            _mod.run_training(file,episodes=20,test_cases=20)
            conn=sqlite3.connect(file)
            conn.execute("UPDATE portfolio_q SET value=99999")
            conn.commit()
            conn.close()
            p=_mod.PortfolioLedger(file)
            try:
                with self.assertRaisesRegex(ValueError,"diverges"):
                    p.verify()
            finally:
                p.close()


if __name__=="__main__":
    unittest.main()
