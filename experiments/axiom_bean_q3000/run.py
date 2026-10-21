"""Execute a real 3,000-episode Q-learning optimization against Axiom sandbox."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
SRC=ROOT/"superforge/integrations/bean_optimization_lab.py"
spec=importlib.util.spec_from_file_location("axiom_bean_q_lab_run",SRC)
module=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=module
spec.loader.exec_module(module)
from bean.optimization.learning_quota import quota

def write_bytes(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out-dir",required=True,type=Path)
    parser.add_argument("--episodes",type=int,default=3000)
    parser.add_argument("--holdout-cases",type=int,default=400)
    parser.add_argument("--verified-fixes-json",type=Path,default=None,
                        help="External evaluator-signed, BEAN-authored source-fix receipts")
    args=parser.parse_args()
    fixes=(json.loads(args.verified_fixes_json.read_text(encoding="utf-8"))
           if args.verified_fixes_json else [])
    key_hex=os.environ.get("BEAN_INDEPENDENT_QUOTA_HMAC_HEX","")
    verifier_key=bytes.fromhex(key_hex) if key_hex else None
    initial=quota(target=args.episodes,q_episodes=0,
                  repair_receipts=fixes,evaluator_key=verifier_key)
    episode_target=initial["remaining"]
    if not episode_target:
        raise ValueError("quota already completed entirely through signed BEAN fixes")
    args.out_dir.mkdir(parents=True,exist_ok=True)
    db=args.out_dir/"axiom-bean-q-learning.sqlite"
    report,trials=module.run_training(
        db,episodes=episode_target,test_cases=args.holdout_cases)
    report["research_quota"]=quota(target=args.episodes,
        q_episodes=report["actual_q_updates"],repair_receipts=fixes,
        evaluator_key=verifier_key)
    if report["research_quota"]["remaining"]:
        raise AssertionError("unfulfilled measured Q + BEAN bugfix quota")
    # The original measured synthetic cases, losses and action candidates
    # are independently recoverable alongside BEAN's compact ledger.
    lines=b"".join(module.canonical(trial)+b"\n" for trial in trials)
    archive=gzip.compress(lines,compresslevel=9,mtime=0)
    trial_path=args.out_dir/"all-synthetic-trials.jsonl.gz"
    write_bytes(trial_path,archive)
    manifest={
        "schema":"axiom.bean.q3000.archive.v1",
        "source_sha256":hashlib.sha256(lines).hexdigest(),
        "compressed_sha256":hashlib.sha256(archive).hexdigest(),
        "records":len(trials),"source_bytes":len(lines),
        "compressed_bytes":len(archive),
        "round_trip_exact":gzip.decompress(archive)==lines}
    if not manifest["round_trip_exact"] or manifest["records"]!=episode_target:
        raise AssertionError("full training history did not recover exactly")
    report["evidence_archive"]=manifest
    report["revision"]=os.environ.get("GITHUB_SHA","local_unpinned")
    report["worker"]={"os":platform.system(),"python":platform.python_version()}
    report.pop("trials",None)
    report_path=args.out_dir/"summary.json"
    write_bytes(report_path,json.dumps(report,sort_keys=True,indent=2).encode("utf-8")+b"\n")
    header={
        "training_episodes":report["training_episodes"],
        "quota":report["research_quota"],
        "actual_q_updates":report["actual_q_updates"],
        "ledger_verification":report["ledger_verify"],
        "before":report["pretraining_validation"]["mean_cost"],
        "independent_holdout":report["independent_holdout"]["mean_cost"],
        "validation_progress":[
            {"episode":x["at_episode"],
             "bean_mean_cost":x["validation"]["mean_cost"]["bean_q"],
             "fifo_mean_cost":x["validation"]["mean_cost"]["fifo"]}
             for x in report["validation_checkpoints"]],
        "archive":manifest}
    print(json.dumps(header,indent=2))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
