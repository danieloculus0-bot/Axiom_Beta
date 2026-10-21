"""BEAN model-free iterative schedule invention versus same-budget search controls.

This is a synthetic scheduling *strategy synthesis* benchmark, not GEPA/OpenHands
execution. Unlike the older four-rule selector, candidates are novel arbitrary
job permutations. It uses the existing BEAN PortfolioLedger Q learner, exact
hash-linked episode receipts and full cold-recoverable candidate trial traces.

Every agent gets the same four seed schedules + 28 measured candidate
evaluations. Returned solutions must be genuine permutations. No LLMs.
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

FILE=Path(__file__).resolve().parents[2]/"superforge/integrations/bean_optimization_lab.py"
spec=importlib.util.spec_from_file_location("axiom_bean_iterative_source",FILE)
lab=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=lab
spec.loader.exec_module(lab)

SCHEMA="axiom.bean.iterative_q.v1"
APP="Axiom_Beta/iterative_schedule_q"
OPERATORS=("swap","insert","reverse","adjacent","target_due","target_family","blend")
ACTION_BUDGET=32
TRAIN_EPISODES=3000
WEIGHTS={"late_sensitive":(5.0,.15,.3),"setup_heavy":(.2,.2,12.0),
         "flow_time":(.15,3.0,.4)}


def digest(obj):
    return hashlib.sha256(lab.canonical(obj)).hexdigest()


def objective(jobs, regime, seq):
    """Independent full-schedule scorer. Matches existing lab.dispatch precisely."""
    if len(seq)!=len(jobs) or set(seq)!={j.identifier for j in jobs}:
        raise ValueError("candidate must be a full, unique permutation")
    if regime not in WEIGHTS:
        raise ValueError("unsupported regime")
    by_id={j.identifier:j for j in jobs}
    elapsed=tardy=flow=changes=0
    family="A"
    for identifier in seq:
        j=by_id[identifier]
        is_setup=(j.family!=family)
        changes+=int(is_setup)
        elapsed+=4*int(is_setup)+j.duration
        tardy+=max(0,elapsed-j.due)
        flow+=elapsed
        family=j.family
    w=WEIGHTS[regime]
    return round(w[0]*tardy+w[1]*flow+w[2]*changes,6)


def seeds(jobs,regime):
    out=[]
    for action in lab.ACTIONS:
        sequence=tuple(lab.dispatch(jobs,action,regime=regime)["sequence"])
        value=objective(jobs,regime,sequence)
        assert math.isclose(value,lab.dispatch(jobs,action,regime=regime)["cost"])
        out.append((action,sequence,value))
    return out


def candidate(seq, jobs, regime, op, rng):
    """Generate an actual new schedule with no observed outcome leakage."""
    n=len(seq)
    arr=list(seq)
    by_id={j.identifier:j for j in jobs}
    if op=="blend":
        op=rng.choice(OPERATORS[:-1])
    if op=="swap":
        i,j=rng.sample(range(n),2)
        arr[i],arr[j]=arr[j],arr[i]
    elif op=="insert":
        i,j=rng.sample(range(n),2)
        item=arr.pop(i)
        arr.insert(j,item)
    elif op=="reverse":
        i,j=sorted(rng.sample(range(n),2))
        arr[i:j+1]=reversed(arr[i:j+1])
    elif op=="adjacent":
        i=rng.randrange(n-1)
        arr[i],arr[i+1]=arr[i+1],arr[i]
    elif op=="target_due":
        # Mutate based on due date, not future schedule outcome.
        i=rng.randrange(1,n)
        chosen=arr.pop(i)
        due=by_id[chosen].due
        earlier=[k for k,x in enumerate(arr) if by_id[x].due>due]
        j=min(earlier) if earlier else rng.randrange(i+1)
        arr.insert(j,chosen)
    elif op=="target_family":
        i=rng.randrange(1,n)
        chosen=arr.pop(i)
        same=[k for k,x in enumerate(arr) if by_id[x].family==by_id[chosen].family]
        j=(rng.choice(same)+1) if same else rng.randrange(n)
        arr.insert(j,chosen)
    else:
        raise ValueError("unknown operator")
    return tuple(arr)


def evaluate_policy(jobs,regime,operator,case_seed, budget=ACTION_BUDGET):
    """All search policies use same evaluator budget; no free objective calls."""
    if not 4<=budget<=128:
        raise ValueError("budget must include four fixed seeds")
    rng=random.Random(case_seed)
    bases=seeds(jobs,regime)
    best_rule,best,best_cost=min(bases,key=lambda item:item[2])
    records=[{"strategy":r,"sequence":list(seq),"cost":cost,
              "accepted":(seq==best)} for r,seq,cost in bases]
    initial=best_cost
    best_seq=best
    accepted=0
    for i in range(budget-4):
        seq=candidate(best_seq,jobs,regime,operator,rng)
        score=objective(jobs,regime,seq)
        ok=score<best_cost-1e-8
        if ok:
            best_seq,best_cost=seq,score
            accepted+=1
        records.append({"op":operator,"sequence":list(seq),"cost":score,
                        "accepted":ok,"trial":i+4})
    assert len(records)==budget
    return {"cost":best_cost,"best_fixed_cost":initial,
            "best_fixed_rule":best_rule,"sequence":list(best_seq),
            "candidate_evaluations":budget,
            "accepted_mutations":accepted,"trace":records}


def state_of(regime,jobs):
    # Observable state only. No target objective or heldout target leakage.
    mean=sum(j.duration for j in jobs)/len(jobs)
    return f"{regime}/{'heavy' if mean>=6 else 'light'}"


def select(q,state,rng,epsilon):
    if rng.random()<epsilon:
        return rng.choice(OPERATORS)
    vals=q._q(APP,state)
    best=max(vals.get(op,0.) for op in OPERATORS)
    return rng.choice([op for op in OPERATORS if math.isclose(
        vals.get(op,0.),best,abs_tol=1e-12)])


class Feedback:
    """Model-free GEPA-inspired reward reflection control with same operators.

    Independent of BEAN's Q table; only sees outcomes of strategies it chose.
    """
    def __init__(self,seed):
        self.rng=random.Random(seed)
        self.history=defaultdict(lambda:defaultdict(list))
        self.policy={}
        self.events=[]
        self.tip="GENESIS"
        self.reflections=0

    def append(self,event):
        item={**event,"prior":self.tip}
        item["digest"]=digest(item)
        self.tip=item["digest"]
        self.events.append(item)

    def choose(self,state,i,total):
        if self.rng.random()<.25-.20*i/max(1,total-1):
            return self.rng.choice(OPERATORS)
        return self.policy.get(state,"blend")

    def observe(self,state,action,reward,case_hash,index):
        self.history[state][action].append(reward)
        self.append({"type":"observed","episode":index,"state":state,
                     "action":action,"reward":reward,"case_hash":case_hash})
        if (index+1)%50!=0:
            return
        for key,h in sorted(self.history.items()):
            eligible=[(sum(vals)/len(vals),len(vals),op)
                      for op,vals in h.items() if len(vals)>=3]
            if not eligible:continue
            score,count,name=max(eligible)
            self.policy[key]=name
            self.reflections+=1
            self.append({"type":"reflection","episode":index+1,
                         "state":key,"chosen":name,
                         "mean_reward":round(score,8),"observations":count})


def train_and_evaluate(out,seed,episodes=TRAIN_EPISODES,holdout_cases=400,
                       budget=ACTION_BUDGET):
    if not 1<=episodes<=3000 or not 10<=holdout_cases<=2000 or not 4<=budget<=128:
        raise ValueError("invalid episode/holdout/evaluation budget")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    db=lab.PortfolioLedger(out/"bean.sqlite")
    feedback=Feedback(seed+781)
    q_rng=random.Random(seed+1507)
    records=[]
    train_score={"q_improved":0,"feedback_improved":0}
    train_hashes=[]
    try:
        if db.verify()["events"]:
            raise ValueError("fresh BEAN ledger required")
        for i in range(episodes):
            regime,jobs=lab.workload(seed,i)
            state=state_of(regime,jobs)
            proof=digest({"regime":regime,"jobs":[asdict(j) for j in jobs]})
            train_hashes.append(proof)
            q_action=select(db,state,q_rng,.30-.25*i/max(1,episodes-1))
            f_action=feedback.choose(state,i,episodes)
            q_result=evaluate_policy(jobs,regime,q_action,seed*5000003+i,budget)
            f_result=evaluate_policy(jobs,regime,f_action,seed*5000003+i,budget)
            prior=q_result["best_fixed_cost"]
            q_reward=(prior-q_result["cost"])/max(prior,1)
            f_reward=(prior-f_result["cost"])/max(prior,1)
            recorded=db.observe(app=APP,event_id=f"q_{i:06d}",
                state=state,action=q_action,reward=round(q_reward,10),
                next_state=None,done=True,evidence_ref="synthetic://"+proof[:40],
                kind="synthetic",revision=SCHEMA,
                tags=("schedule","iterated","measured"))
            assert recorded["new"]
            feedback.observe(state,f_action,round(f_reward,10),proof,i)
            train_score["q_improved"]+=int(q_result["cost"]<prior)
            train_score["feedback_improved"]+=int(f_result["cost"]<prior)
            records.append({"episode":i,"case_sha256":proof,"regime":regime,
                            "state":state,"q_action":q_action,"f_action":f_action,
                            "q_reward":q_reward,"feedback_reward":f_reward,
                            "q":q_result,"feedback":f_result,
                            "bean_receipt":recorded["receipt"]})
        replay=db.verify()
        assert replay["events"]==replay["rewarded_events"]==episodes
        # Frozen holdout across both policies. Same objective evaluations/case.
        policy_seed=seed+200000
        sums={"BEAN_Q":0.,"feedback_reflection":0.,"random_untrained":0.,
              "blend_untrained":0.,"best_fixed_per_case":0.,"fifo":0.}
        won={"BEAN_Q":0,"feedback_reflection":0,"random_untrained":0,
             "blend_untrained":0}
        cold=[]
        untrained_rng=random.Random(seed+739)
        selected=defaultdict(lambda:defaultdict(int))
        for i in range(holdout_cases):
            regime,jobs=lab.workload(policy_seed,i)
            state=state_of(regime,jobs)
            case_hash=digest({"regime":regime,"jobs":[asdict(j) for j in jobs]})
            ops={"BEAN_Q":select(db,state,q_rng,epsilon=0),
                 "feedback_reflection":feedback.policy.get(state,"blend"),
                 "random_untrained":untrained_rng.choice(OPERATORS),
                 "blend_untrained":"blend"}
            trial={}
            for label,op in ops.items():
                result=evaluate_policy(jobs,regime,op,
                                       policy_seed*5000003+i,budget)
                sums[label]+=result["cost"]
                won[label]+=int(result["cost"]<result["best_fixed_cost"]-1e-8)
                selected[label][op]+=1
                trial[label]={"action":op,"cost":result["cost"],
                              "sequence":result["sequence"],
                              "accepted_mutations":result["accepted_mutations"],
                              "trace":result["trace"]}
            rules=seeds(jobs,regime)
            sums["best_fixed_per_case"]+=min(x[2] for x in rules)
            sums["fifo"]+=next(x[2] for x in rules if x[0]=="fifo")
            cold.append({"episode":i,"regime":regime,"case_sha256":case_hash,
                         "results":trial})
        frozen={"cases":holdout_cases,"seed":policy_seed,
                "average_cost":{k:round(x/holdout_cases,6) for k,x in sums.items()},
                "beaten_best_fixed_case_count":won,
                "selections":{k:dict(v) for k,v in selected.items()},
                "holdout_sha256":digest([x["case_sha256"] for x in cold]),
                "all_trace_sha256":digest(cold)}
        full=lab.canonical({"train_cases":records,
                            "holdout_cases":cold,
                            "feedback_events":feedback.events,
                            "train_source_hashes":train_hashes})
        packed=gzip.compress(full,compresslevel=9,mtime=0)
        assert gzip.decompress(packed)==full
        (out/"all_exact_trials.json.gz").write_bytes(packed)
        report={"schema":SCHEMA,"train_seed":seed,"episodes":episodes,
                "evaluation_budget_per_case":budget,"Q_updates":episodes,
                "learning_engine":"BEAN PortfolioLedger Q on novel permutation operators",
                "feedback_engine":"Model-free feedback policy mutation, not official GEPA",
                "OpenHands_executed":False,"GEPA_executed":False,
                "LLM_calls":0,"training_improved_cases":train_score,
                "frozen_holdout":frozen,
                "ledger":replay,"feedback_tip":feedback.tip,
                "feedback_reflections":feedback.reflections,
                "archive":{"bytes":len(packed),"source_bytes":len(full),
                           "sha256":hashlib.sha256(packed).hexdigest(),
                           "source_sha256":hashlib.sha256(full).hexdigest(),
                           "lossless_roundtrip":True}}
        (out/"summary.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
        return report
    finally:
        db.close()


def run_all(folder,seeds_in=(1093,2003,3019),episodes=3000,cases=400,budget=32):
    folder=Path(folder)
    results=[train_and_evaluate(folder/str(s),s,episodes,cases,budget)
             for s in seeds_in]
    labels=("BEAN_Q","feedback_reflection","random_untrained",
            "blend_untrained","best_fixed_per_case","fifo")
    averages={k:round(sum(r["frozen_holdout"]["average_cost"][k]
                          for r in results)/len(results),6) for k in labels}
    winners=[]
    for r in results:
        x=r["frozen_holdout"]["average_cost"]
        cmp=x["BEAN_Q"]-x["feedback_reflection"]
        winners.append("BEAN" if cmp < -0.00001 else
                       "feedback" if cmp>0.00001 else "tie")
    summary={"schema":SCHEMA,"Q_updates_total":episodes*len(results),
             "feedback_training_cases_total":episodes*len(results),
             "unseen_holdout_cases_total":cases*len(results),
             "seed_results":[{"seed":r["train_seed"],
                              "holdout":r["frozen_holdout"],
                              "Q_ledger_tip":r["ledger"]["tip"]}
                              for r in results],
             "holdout_means":averages,"winners_vs_feedback":winners,
             "official_GEPA_runs":0,"OpenHands_runs":0,"LLM_calls":0,
             "same_candidate_evaluation_budget":budget}
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"comparison.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    return summary
