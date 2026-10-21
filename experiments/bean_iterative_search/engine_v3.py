"""BEAN v3 logical scheduling search: combinatorial structure + learned refinement.

All policies receive exactly 32 objective evaluations per 8-job scheduling
instance. BEAN composes NEW permutations by enumerating six possible job-family
orders and three internal priority logics, then spends ten remaining evaluations
on learned targeted edits. Separately compare an untrained identical algorithm
with random local operator and the existing model-free feedback benchmark.

Human-coded domain operators are NOT neural self-invention; genuine BEAN Q
learning controls the final refinement operator, measured by a sealed holdout.
"""
from __future__ import annotations

from collections import Counter,defaultdict
from dataclasses import asdict
import gzip
import hashlib
import importlib.util
from itertools import permutations
import json
import math
from pathlib import Path
import random
import sys

HERE=Path(__file__).resolve().parent/"engine.py"
spec=importlib.util.spec_from_file_location("axiom_bean_logic_v3_parent",HERE)
v1=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=v1
spec.loader.exec_module(v1)

APP="Axiom_Beta/logic_scheduling_q_v3"
SCHEMA="axiom.bean.logic_permutation_q.v3"
MODES=("due","short","slack")
BUDGET=32


def structured_sequences(jobs):
    """Exactly 18 candidate schedules, generated WITHOUT accessing outcomes."""
    byfam=defaultdict(list)
    for j in jobs:
        byfam[j.family].append(j)
    groups=sorted(byfam)
    if groups!=["A","B","C"]:
        raise ValueError("research fixture requires all three families")
    made=[]
    for order in permutations(groups):
        for mode in MODES:
            seq=[]
            for family in order:
                items=byfam[family]
                if mode=="due":
                    items=sorted(items,key=lambda j:(j.due,j.duration,j.identifier))
                elif mode=="short":
                    items=sorted(items,key=lambda j:(j.duration,j.due,j.identifier))
                else:
                    items=sorted(items,key=lambda j:(j.due-j.duration,j.due,j.identifier))
                seq.extend(j.identifier for j in items)
            made.append((mode+"-"+ "".join(order),tuple(seq)))
    assert len(made)==18
    return made


def valid_case(jobs):
    return {j.family for j in jobs}=={"A","B","C"}


def context(regime,jobs):
    return v1.state_of(regime,jobs)


def select(q,state,rng,epsilon):
    if rng.random()<epsilon:
        return rng.choice(v1.OPERATORS)
    vals=q._q(APP,state)
    high=max(vals.get(op,0.) for op in v1.OPERATORS)
    return rng.choice([op for op in v1.OPERATORS if math.isclose(
        vals.get(op,0.),high,abs_tol=1e-12)])


def run_search(jobs,regime,operator,seed, budget=BUDGET):
    """Four fixed + eighteen structured + ten local edits = 32 exact calls."""
    if budget!=32:
        raise ValueError("this fair-budget benchmark requires 32 evaluations")
    rng=random.Random(seed)
    bases=v1.seeds(jobs,regime)
    initial=min(x[2] for x in bases)
    name,best,cost=min(bases,key=lambda x:x[2])
    history=[{"source":"fixed:"+label,"seq":list(seq),"cost":v}
             for label,seq,v in bases]
    constructed=0
    for label,seq in structured_sequences(jobs):
        score=v1.objective(jobs,regime,seq)
        history.append({"source":"structured:"+label,"seq":list(seq),
                        "cost":score})
        if score<cost-1e-8:
            best,cost=seq,score
            constructed+=1
    structured_cost=cost
    improved_local=0
    for i in range(10):
        proposed=v1.candidate(best,jobs,regime,operator,rng)
        val=v1.objective(jobs,regime,proposed)
        if val<cost-1e-8:
            best,cost=proposed,val
            improved_local+=1
        history.append({"source":"mutation:"+operator,
                        "seq":list(proposed),"cost":val})
    if len(history)!=budget:
        raise AssertionError("incorrect objective evaluation budget")
    if cost>structured_cost+1e-9 or structured_cost>initial+1e-9:
        raise AssertionError("best solution must be nonworsening")
    assert v1.objective(jobs,regime,best)==cost
    return {"operator":operator,"cost":cost,
            "initial_cost":initial,"structured_cost":structured_cost,
            "structured_improvements":constructed,
            "local_improvements":improved_local,
            "best_sequence":list(best),
            "objective_evaluations":budget,"trace":history}


def run_seed(out,seed,train_cases=3000,holdout=400,holdout_offset=600000):
    if not 1<=train_cases<=3000 or not 10<=holdout<=2000:
        raise ValueError("invalid budget")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    ledger=v1.lab.PortfolioLedger(out/"q.sqlite")
    feedback=v1.Feedback(seed+781)
    rng=random.Random(seed+3001)
    observed=[]
    skipped=0
    try:
        if ledger.verify()["events"]:
            raise ValueError("fresh research ledger required")
        # A given case may lack one of the three job families.
        # Account transparently for skipped cases instead of inventing data.
        index=0
        n=0
        while n<train_cases:
            regime,jobs=v1.lab.workload(seed,index)
            index+=1
            if not valid_case(jobs):
                skipped+=1
                continue
            state=context(regime,jobs)
            op=select(ledger,state,rng,.30-.25*n/max(1,train_cases-1))
            case_id=v1.digest({"regime":regime,"jobs":[asdict(j) for j in jobs]})
            proposed=run_search(jobs,regime,op,seed*7000003+index)
            step_reward=(proposed["structured_cost"]-proposed["cost"])/max(
                1,proposed["structured_cost"])
            reward=round(step_reward if step_reward>0 else -.002,10)
            res=ledger.observe(app=APP,event_id=f"v3_{n:06d}",
                state=state,action=op,reward=reward,next_state=None,
                done=True,evidence_ref="synthetic://"+case_id[:40],
                kind="synthetic",revision=SCHEMA,tags=("schedule","reasoning"))
            if not res["new"]:raise AssertionError("duplicate source event")
            control_op=feedback.choose(state,n,train_cases)
            f_run=v1.evaluate_policy(jobs,regime,control_op,
                                      seed*7000003+index,32)
            f_reward=(f_run["best_fixed_cost"]-f_run["cost"])/max(
                1,f_run["best_fixed_cost"])
            feedback.observe(state,control_op,round(f_reward,10),case_id,n)
            observed.append({"source_index":index-1,"case_sha256":case_id,
                             "operator":op,"reward":reward,
                             "BEAN":proposed,
                             "feedback_op":control_op,
                             "feedback":f_run,"Q_receipt":res["receipt"]})
            n+=1
        verified=ledger.verify()
        if verified["rewarded_events"]!=train_cases:
            raise AssertionError("no real 1-per-case Q updates")
        controls=random.Random(seed+9017)
        held=[]
        hold_index=0
        missed=0
        counts=Counter()
        costs=defaultdict(float)
        strong=defaultdict(int)
        source=seed+holdout_offset
        while len(held)<holdout:
            regime,jobs=v1.lab.workload(source,hold_index)
            hold_index+=1
            if not valid_case(jobs):
                missed+=1
                continue
            st=context(regime,jobs)
            op=select(ledger,st,rng,epsilon=0)
            counts[op]+=1
            case_seed=source*7000003+hold_index
            bean=run_search(jobs,regime,op,case_seed)
            ablation=run_search(jobs,regime,
                                controls.choice(v1.OPERATORS),case_seed)
            f_op=feedback.policy.get(st,"blend")
            comparison=v1.evaluate_policy(jobs,regime,f_op,case_seed,32)
            methods={"BEAN_Q_logic":bean,
                     "same_logic_without_Q":ablation,
                     "feedback_reflection":comparison}
            fixed=bean["initial_cost"]
            for label,item in methods.items():
                value=item["cost"]
                costs[label]+=value
                strong[label]+=int(value<fixed-1e-8)
                evals=item.get("objective_evaluations",item.get("candidate_evaluations"))
                assert evals==32
            costs["best_fixed"]+=fixed
            costs["fifo"]+=v1.lab.dispatch(jobs,"fifo",regime=regime)["cost"]
            held.append({"case_sha256":v1.digest({
                "regime":regime,"jobs":[asdict(j) for j in jobs]}),
                         "regime":regime,"Q_operator":op,
                         "feedback_operator":f_op,"results":methods})
        if ledger.verify()!=verified:
            raise AssertionError("holdout changed Q policy")
        raw=v1.lab.canonical({"train":observed,"heldout":held,
                              "feedback_history":feedback.events})
        package=gzip.compress(raw,compresslevel=9,mtime=0)
        assert gzip.decompress(package)==raw
        (out/"complete_trials.json.gz").write_bytes(package)
        result={"schema":SCHEMA,"seed":seed,"training_cases":train_cases,
                "train_source_cases_rejected_missing_family":skipped,
                "holdout_source_cases_rejected_missing_family":missed,
                "holdout_cases":holdout,
                "Q_updates":verified["rewarded_events"],
                "Q_receipt_tip":verified["tip"],
                "frozen_holdout_seed":source,
                "frozen_holdout_sha256":v1.digest([r["case_sha256"] for r in held]),
                "mean_cost":{k:round(v/holdout,6) for k,v in costs.items()},
                "beaten_fixed_cases":dict(strong),
                "operator_counts":dict(counts),
                "archive":{"compressed_bytes":len(package),
                           "sha256":hashlib.sha256(package).hexdigest(),
                           "recovered_original":True},
                "candidate_budget":32,
                "model_calls":0,
                "official_GEPA_executed":False,"OpenHands_executed":False}
        (out/"summary.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        return result
    finally:
        ledger.close()


def run_all(out,seeds=(1093,2003,3019),train_cases=3000,heldout=400):
    out=Path(out)
    scores=[run_seed(out/str(s),s,train_cases,heldout) for s in seeds]
    means={key:round(sum(x["mean_cost"][key] for x in scores)/len(scores),6)
           for key in ("BEAN_Q_logic","same_logic_without_Q",
                       "feedback_reflection","best_fixed","fifo")}
    winners=[]
    for x in scores:
        q=x["mean_cost"]["BEAN_Q_logic"]
        f=x["mean_cost"]["feedback_reflection"]
        winners.append("BEAN" if q<f-1e-8 else "feedback" if q>f+1e-8 else "tie")
    summary={"schema":SCHEMA,
             "train_cases":len(seeds)*train_cases,
             "actual_Q_updates":len(seeds)*train_cases,
             "holdout_cases":len(seeds)*heldout,
             "model_calls":0,"budget_per_policy_per_case":32,
             "holdout_mean_cost":means,"per_seed_winners":winners,
             "seeds":[{"seed":s["seed"],"holdout":s["mean_cost"],
                       "Q_tip":s["Q_receipt_tip"],
                       "holdout_sha256":s["frozen_holdout_sha256"]}
                       for s in scores],
             "official_GEPA_executed":False,"OpenHands_executed":False}
    (out/"comparison.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    return summary
