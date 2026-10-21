"""BEAN v2: Q-guided, per-block logic, contextual tactic switching and escape.

No LLM. BEAN trains real PortfolioLedger Q values on measured outcomes every
four candidate evaluations. Frozen holdout never modifies Q; in-case adaptation
uses only already-measured schedule cost and counts toward 32-eval budget.

Control: original diagnostic feedback optimizer from engine.py, same task and
32 evaluator calls, plus same adaptive search with Q values removed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import sys

HERE=Path(__file__).resolve().parent/"engine.py"
spec=importlib.util.spec_from_file_location("axiom_bean_iterative_v1",HERE)
v1=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=v1
spec.loader.exec_module(v1)

SCHEMA="axiom.bean.iterative_q_blocks.v2"
APP="Axiom_Beta/iterative_scheduling_Q_block"
BUDGET=32
BLOCK=4


def decide(q,state,rng,explore,local_quality=None):
    if rng.random()<explore:
        return rng.choice(v1.OPERATORS)
    vals=q._q(APP,state) if q is not None else {}
    local_quality=local_quality or {}
    # Modest local encouragement; Q remains the learned global value.
    values={op:vals.get(op,0.0)+.015*local_quality.get(op,0)
            for op in v1.OPERATORS}
    best=max(values.values())
    return rng.choice([k for k,v in values.items()
                       if math.isclose(v,best,abs_tol=1e-12)])


def search(jobs,regime,case_seed, *,q=None,episode=0,
           train=False,explore=0.0,budget=BUDGET):
    if budget<8 or budget>128 or (budget-4)%BLOCK!=0:
        raise ValueError("budget must be 4+4n, 8..128")
    rng=random.Random(case_seed)
    bases=v1.seeds(jobs,regime)
    _,base_seq,base_cost=min(bases,key=lambda e:e[2])
    incumbent,incumbent_cost=base_seq,base_cost
    archive=sorted({tuple(seq):cost for _,seq,cost in bases}.items(),
                   key=lambda x:x[1])
    records=[{"source":name,"seq":list(seq),"cost":cost}
             for name,seq,cost in bases]
    state_root=v1.state_of(regime,jobs)
    local_quality=defaultdict(int)
    block_records=[]
    stalled=0
    case_hash=v1.digest({"regime":regime,
                         "jobs":[asdict(j) for j in jobs]})
    for block in range((budget-4)//BLOCK):
        state=f"{state_root}/phase{min(block//2,3)}/stall{int(stalled>=4)}"
        action=decide(q,state,rng,explore,
                      local_quality if q is not None else None)
        start=incumbent_cost
        observed=0
        for index in range(BLOCK):
            # Track promising alternatives; deterministic escapes count as
            # evaluations when their mutations are scored.
            parent=incumbent
            if stalled>=5 and len(archive)>1 and index==0:
                parent=archive[rng.randrange(min(3,len(archive)))][0]
            seq=v1.candidate(parent,jobs,regime,action,rng)
            scored=v1.objective(jobs,regime,seq)
            improved=scored<incumbent_cost-1e-8
            if improved:
                incumbent,incumbent_cost=seq,scored
                local_quality[action]+=1
                observed+=1
                stalled=0
            else:
                stalled+=1
            archive.append((seq,scored))
            archive.sort(key=lambda x:x[1])
            archive=archive[:5]
            records.append({"source":action,"seq":list(seq),
                            "cost":scored,"improved":improved,
                            "block":block})
        reward=round((start-incumbent_cost)/max(1,start),10)
        # No reward for stalled search. Signed reward with a small penalty
        # makes failure visible in Q instead of awarding every attempt.
        if reward==0:
            reward=-0.002
        block_evidence={"block":block,"episode":episode,"state":state,
                        "action":action,"before":start,
                        "after":incumbent_cost,
                        "reward":reward,"improved":observed,
                        "case_hash":case_hash}
        if train:
            if q is None:
                raise ValueError("training needs persistent BEAN Q ledger")
            observed_id=f"v2_{episode:06d}_{block:02d}"
            receipt=q.observe(app=APP,event_id=observed_id,
                state=state,action=action,reward=reward,next_state=None,
                done=True,evidence_ref="synthetic://"+v1.digest(block_evidence)[:40],
                kind="synthetic",revision=SCHEMA,
                tags=("iterative","learned","synthetic"))
            assert receipt["new"],"duplicate Q learning update"
            block_evidence["Q_receipt"]=receipt["receipt"]
        block_records.append(block_evidence)
    if len(records)!=budget or incumbent_cost>base_cost:
        raise AssertionError("search budget or monotonic-best invariant broken")
    return {"cost":incumbent_cost,"initial":base_cost,
            "sequence":list(incumbent),"evaluations":len(records),
            "blocks":block_records,"trace":records,
            "improvement_pct":100*(base_cost-incumbent_cost)/max(1,base_cost)}


def train_and_compare(out,seed,episodes=3000,holdout=400,budget=BUDGET,
                      holdout_offset=400000):
    if not 1<=episodes<=3000 or not 10<=holdout<=2000 or budget!=32:
        raise ValueError("invalid budget or dataset sizes")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    ledger=v1.lab.PortfolioLedger(out/"bean-blocks.sqlite")
    feedback=v1.Feedback(seed+781)
    train_log=[]
    train_seeds=[]
    try:
        if ledger.verify()["events"]:
            raise ValueError("separate fresh BEAN ledger required")
        for i in range(episodes):
            regime,jobs=v1.lab.workload(seed,i)
            case_hash=v1.digest({"regime":regime,
                                 "jobs":[asdict(j) for j in jobs]})
            train_seeds.append(case_hash)
            qresult=search(jobs,regime,seed*700001+i,
                           q=ledger,episode=i,train=True,
                           explore=.32-.28*i/max(1,episodes-1),
                           budget=budget)
            action=feedback.choose(v1.state_of(regime,jobs),i,episodes)
            fresult=v1.evaluate_policy(jobs,regime,action,
                                       seed*700001+i,budget)
            reward=(fresult["best_fixed_cost"]-fresult["cost"])/max(
                1,fresult["best_fixed_cost"])
            feedback.observe(v1.state_of(regime,jobs),action,
                             round(reward,10),case_hash,i)
            train_log.append({"case":case_hash,"Q_search":qresult,
                              "feedback_action":action,
                              "feedback_search":fresult})
        replay=ledger.verify()
        intended=episodes*(budget-4)//BLOCK
        if replay["rewarded_events"]!=intended:
            raise AssertionError("BEAN Q update count does not match blocks")
        sums=defaultdict(float)
        victories=defaultdict(int)
        cases=[]
        offset_seed=seed+holdout_offset
        for i in range(holdout):
            regime,jobs=v1.lab.workload(offset_seed,i)
            case_hash=v1.digest({"regime":regime,"jobs":[asdict(j) for j in jobs]})
            qresult=search(jobs,regime,offset_seed*700001+i,
                           q=ledger,train=False,explore=0,budget=budget)
            f_action=feedback.policy.get(v1.state_of(regime,jobs),"blend")
            fresult=v1.evaluate_policy(jobs,regime,f_action,
                                       offset_seed*700001+i,budget)
            ablation=search(jobs,regime,offset_seed*700001+i,
                            q=None,train=False,explore=1.0,budget=budget)
            normal=v1.evaluate_policy(jobs,regime,"blend",
                                      offset_seed*700001+i,budget)
            methods={"BEAN_Q_adaptive":qresult,"feedback_static":fresult,
                     "untrained_adaptive":ablation,"untrained_blend":normal}
            for method,result in methods.items():
                sums[method]+=result["cost"]
                victories[method]+=int(result["cost"]<qresult["initial"]-1e-8)
                if ((result.get("evaluations",result.get("candidate_evaluations"))
                        !=budget)):
                    raise AssertionError("budget mismatch")
            sums["best_fixed"]+=qresult["initial"]
            sums["fifo"]+=v1.lab.dispatch(jobs,"fifo",regime=regime)["cost"]
            cases.append({"id":i,"case_sha256":case_hash,"regime":regime,
                          "results":methods,
                          "feedback_action":f_action})
        if ledger.verify()!=replay:
            raise AssertionError("cold holdout illegally updated BEAN's Q ledger")
        audit={"train":train_log,"holdout":cases,
               "feedback_events":feedback.events,
               "training_source_hashes":train_seeds}
        raw=v1.lab.canonical(audit)
        compressed=gzip.compress(raw,compresslevel=9,mtime=0)
        assert gzip.decompress(compressed)==raw
        (out/"exact_training_and_holdout.json.gz").write_bytes(compressed)
        report={"schema":SCHEMA,"seed":seed,
                "train_cases":episodes,
                "holdout_cases":holdout,
                "q_updates":intended,
                "source":"synthetic",
                "evaluations_per_case":budget,
                "holdout_seed":offset_seed,
                "holdout_mean_cost":{k:round(v/holdout,6) for k,v in sums.items()},
                "improvement_cases":dict(victories),
                "frozen_holdout_sha256":v1.digest([c["case_sha256"] for c in cases]),
                "Q_ledger":replay,
                "feedback_tip":feedback.tip,
                "cold_evidence":{"archive_sha256":hashlib.sha256(compressed).hexdigest(),
                                 "original_sha256":hashlib.sha256(raw).hexdigest(),
                                 "records":episodes+holdout,
                                 "roundtrip_exact":True},
                "official_GEPA_executed":False,"OpenHands_executed":False,
                "language_model_calls":0}
        (out/"summary.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
        return report
    finally:
        ledger.close()


def run(out,seeds=(1093,2003,3019),episodes=3000,holdout=400,budget=32):
    out=Path(out)
    results=[train_and_compare(out/str(s),s,episodes,holdout,budget)
             for s in seeds]
    tags=("BEAN_Q_adaptive","feedback_static","untrained_adaptive",
          "untrained_blend","best_fixed","fifo")
    means={k:round(sum(r["holdout_mean_cost"][k] for r in results)/len(results),6)
           for k in tags}
    winners=[]
    for r in results:
        a=r["holdout_mean_cost"]
        delta=a["BEAN_Q_adaptive"]-a["feedback_static"]
        winners.append("BEAN" if delta < -.000001 else
                       "feedback" if delta > .000001 else "tie")
    rep={"schema":SCHEMA,
         "total_training_cases":episodes*len(results),
         "total_Q_learning_updates":episodes*len(results)*7,
         "total_frozen_holdout_cases":holdout*len(results),
         "budgets_equal":budget,
         "means":means,"winners":winners,
         "each_seed":[{"seed":r["seed"],"holdout":r["holdout_mean_cost"],
                       "Q_tip":r["Q_ledger"]["tip"],
                       "holdout_sha256":r["frozen_holdout_sha256"]}
                      for r in results],
         "model_calls":0,"official_gepa_runs":0,"openhands_runs":0}
    (out/"comparison.json").write_text(json.dumps(rep,sort_keys=True,indent=2)+"\n")
    return rep
