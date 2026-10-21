"""Run 9000 model-free Axiom scheduling Q trials with 18+10 candidate invention."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent/"engine_v3.py"
spec=importlib.util.spec_from_file_location("axiom_bean_v3_runner",HERE)
engine=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=engine
spec.loader.exec_module(engine)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--episodes",default=3000,type=int)
    parser.add_argument("--holdout",default=400,type=int)
    opt=parser.parse_args()
    score=engine.run_all(opt.out,train_cases=opt.episodes,
                         heldout=opt.holdout)
    print(json.dumps({
        "actual_Q_updates":score["actual_Q_updates"],
        "train_cases":score["train_cases"],
        "holdout_cases":score["holdout_cases"],
        "mean_cost":score["holdout_mean_cost"],
        "per_seed_winners_vs_feedback":score["per_seed_winners"],
        "official_GEPA_executed":score["official_GEPA_executed"],
        "OpenHands_executed":score["OpenHands_executed"],
        "language_model_calls":score["model_calls"]},indent=2))
