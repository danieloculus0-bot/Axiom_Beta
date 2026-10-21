"""Three-seed BEAN versus model-free feedback policy optimizer experiment."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"experiments/bean_model_free_comparison/benchmark.py"
spec=importlib.util.spec_from_file_location("axiom_bean_model_free_comparison",SOURCE)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out-dir",required=True,type=Path)
    p.add_argument("--episodes",type=int,default=3000)
    p.add_argument("--holdout",type=int,default=400)
    args=p.parse_args()
    report=module.run(args.out_dir,episodes=args.episodes,holdout_cases=args.holdout)
    print(json.dumps({"schema":report["schema"],
                     "beAN_real_Q_updates":report["total_BEAN_Q_updates"],
                     "feedback_training_cases":report["total_feedback_training_cases"],
                     "wins":report["per_seed_winner"],
                     "holdout_costs":report["holdout_mean_cost_across_seeds"],
                     "actual_opensource_framework_runs":{
                         "official_gepa":report["actual_gepa_runs"],
                         "openhands":report["actual_openhands_runs"]},
                     "language_model_calls":report["language_model_calls"]},
                     indent=2))

if __name__=="__main__":
    main()
