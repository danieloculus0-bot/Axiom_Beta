"""Execute 9000 real BEAN Q updates versus comparable logic-only optimizers."""
from pathlib import Path
import argparse
import importlib.util
import json
import sys

HERE=Path(__file__).resolve().parent/"engine.py"
spec=importlib.util.spec_from_file_location("axiom_bean_iterative_run",HERE)
engine=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=engine
spec.loader.exec_module(engine)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--episodes",type=int,default=3000)
    p.add_argument("--cases",type=int,default=400)
    p.add_argument("--budget",type=int,default=32)
    args=p.parse_args()
    x=engine.run_all(args.out,episodes=args.episodes,
                     cases=args.cases,budget=args.budget)
    print(json.dumps({"q_updates":x["Q_updates_total"],
        "feedback_train_cases":x["feedback_training_cases_total"],
        "frozen_cases":x["unseen_holdout_cases_total"],
        "budget":x["same_candidate_evaluation_budget"],
        "holdout_costs":x["holdout_means"],
        "winners_vs_feedback":x["winners_vs_feedback"],
        "language_model_calls":x["LLM_calls"],
        "official_GEPA_runs":x["official_GEPA_runs"],
        "OpenHands_runs":x["OpenHands_runs"]},indent=2))

if __name__=="__main__":
    main()
