"""Full BEAN contextual per-block Q optimization benchmark, no LLM."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
FILE=Path(__file__).resolve().parent/"engine_v2.py"
spec=importlib.util.spec_from_file_location("axiom_bean_v2_runner",FILE)
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--episodes",default=3000,type=int)
    p.add_argument("--holdout",default=400,type=int)
    a=p.parse_args()
    results=m.run(a.out,episodes=a.episodes,holdout=a.holdout)
    print(json.dumps({"Q_learning_updates":results["total_Q_learning_updates"],
                      "train_cases":results["total_training_cases"],
                      "unseen_cases":results["total_frozen_holdout_cases"],
                      "holdout_means":results["means"],
                      "winners_vs_feedback":results["winners"],
                      "official_GEPA_runs":results["official_gepa_runs"],
                      "OpenHands_runs":results["openhands_runs"],
                      "language_model_calls":results["model_calls"]},indent=2))
