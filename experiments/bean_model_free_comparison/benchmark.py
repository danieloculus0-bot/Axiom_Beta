"""Model-free Axiom optimizer comparison.

Actual BEAN Core PortfolioLedger Q learning versus an independent GEPA-inspired
diagnostic / policy-mutation control. The latter is NOT the official GEPA
package, does NOT run an LLM, and is not OpenHands.

Both systems receive identical synthetic training cases, 4 dispatch actions,
measured cost and FIFO reward, 3 distinct seeds and an untouched holdout.
No real employee/job data or live Axiom database is accessed.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys

SRC=Path(__file__).resolve().parents[2]/"superforge/integrations/bean_optimization_lab.py"
spec=importlib.util.spec_from_file_location("axiom_bean_compare_lab",SRC)
lab=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=lab
spec.loader.exec_module(lab)

SCHEMA="axiom.bean.model_free_comparison.v1"
WEIGHTS={"late_sensitive":(5.0,0.15,0.3),
         "setup_heavy":(0.2,0.2,12.0),
         "flow_time":(0.15,3.0,0.4)}


def sha(x):
    return hashlib.sha256(lab.canonical(x)).hexdigest()


class DiagnosticMutation:
    """Feedback-policy mutation inspired by reflective search, NOT official GEPA.

    Mutations are attempted on fixed intervals, using only *observed* action
    outcomes. No unseen-action oracle, no holdout observations, no language
    model and no target test-set leakage.
    """
    def __init__(self,seed):
        self.rng=random.Random(seed)
        self.policy={}
        self.history=defaultdict(lambda:defaultdict(list))
        self.events=[]
        self.tip="GENESIS"

    def record(self,event):
        event=dict(event)
        event["previous_hash"]=self.tip
        event["chain_hash"]=sha([self.tip,event])
        self.tip=event["chain_hash"]
        self.events.append(event)

    def choose(self,state,index,total):
        epsilon=.38-.30*index/max(1,total-1)
        if self.rng.random()<epsilon:
            return self.rng.choice(lab.ACTIONS)
        return self.policy.get(state,"fifo")

    def train(self,seed,episodes):
        for index in range(episodes):
            regime,jobs=lab.workload(seed,index)
            state=lab.state_for(regime,jobs)
            action=self.choose(state,index,episodes)
            score=lab.dispatch(jobs,action,regime=regime)
            fifo=lab.dispatch(jobs,"fifo",regime=regime)
            reward=(fifo["cost"]-score["cost"])/max(1,fifo["cost"])
            w=WEIGHTS[regime]
            diagnostics={
                "weighted_lateness":round(w[0]*score["tardiness"],6),
                "weighted_flow":round(w[1]*score["flow_time"],6),
                "weighted_setup":round(w[2]*score["setups"],6)}
            case_hash=sha([regime,[asdict(j) for j in jobs]])
            observation={"reward":reward,"cost":score["cost"],
                         "diagnostics":diagnostics}
            self.history[state][action].append(observation)
            self.record({"type":"observed_case",
                         "episode":index,
                         "case_sha256":case_hash,
                         "state":state,"action":action,
                         "outcome":observation,
                         "source":"synthetic"})
            if (index+1)%50==0 or index+1==episodes:
                self.reflect(index+1)
        return {"cases":episodes,"receipts":len(self.events),
                "reflections":sum(x["type"]=="reflection" for x in self.events),
                "ledger_tip":self.tip,
                "ledger_sha256":sha(self.events),
                "policy":dict(sorted(self.policy.items()))}

    def reflect(self,episode):
        for state,seen_by_action in sorted(self.history.items()):
            scored=[]
            for action in lab.ACTIONS:
                history=seen_by_action[action]
                if len(history)<3:
                    continue
                avg=sum(x["reward"] for x in history)/len(history)
                # Diagnostic attribution is used to explain attempted policy
                # mutation; reward remains independently measured.
                dominant=max(
                    ("weighted_lateness","weighted_flow","weighted_setup"),
                    key=lambda term:sum(v["diagnostics"][term] for v in history)
                                    /len(history))
                scored.append({"action":action,"mean_reward":round(avg,8),
                               "examples":len(history),
                               "dominant_cost_term":dominant})
            if not scored:
                continue
            proposal=max(scored,key=lambda r:(r["mean_reward"],r["examples"]))
            current=self.policy.get(state,"fifo")
            # The candidate MUST have empirical advantage over the incumbent
            # on collected observations; doing nothing is a valid proposal.
            inc=next((x for x in scored if x["action"]==current),None)
            accepted=(proposal["action"]!=current and
                      proposal["mean_reward"]>(inc["mean_reward"] if inc else 0))
            if accepted:
                self.policy[state]=proposal["action"]
            self.record({"type":"reflection","episode":episode,
                         "state":state,"incumbent":current,
                         "proposal":proposal,"accepted":accepted,
                         "alternatives":scored})

    def act(self,state):
        return self.policy.get(state,"fifo")


def frozen_evaluation(policy,seed,cases):
    results=[]
    totals=0.
    decisions={a:0 for a in lab.ACTIONS}
    for episode in range(cases):
        regime,jobs=lab.workload(seed,episode)
        state=lab.state_for(regime,jobs)
        action=policy.act(state)
        result=lab.dispatch(jobs,action,regime=regime)
        totals+=result["cost"]
        decisions[action]+=1
        results.append({"case_sha256":sha([regime,[asdict(j) for j in jobs]]),
                        "action":action,"cost":result["cost"]})
    return {"mean_cost":round(totals/cases,6),
            "decision_counts":decisions,"cases":cases,
            "replay_sha256":sha(results)}


def one_seed(out,seed,episodes=3000,holdout_cases=400):
    if not 1<=episodes<=3000 or not 10<=holdout_cases<=2000:
        raise ValueError("invalid comparison budget")
    out=Path(out)
    out.mkdir(parents=True,exist_ok=True)
    validate_seed=seed+100000
    holdout_seed=seed+200000
    bean,bean_trials=lab.run_training(
        out/"bean.sqlite",episodes=episodes,train_seed=seed,
        validate_seed=validate_seed,holdout_seed=holdout_seed,
        test_cases=holdout_cases)
    feedback=DiagnosticMutation(seed+881)
    summary=feedback.train(seed,episodes)
    alternative=frozen_evaluation(feedback,holdout_seed,holdout_cases)
    # Same literal seeds, fixtures and action space; all holdout cases are
    # evaluated only AFTER either training ends.
    own=bean["independent_holdout"]
    assert own["cases"]==alternative["cases"]==holdout_cases
    assert sum(alternative["decision_counts"].values())==holdout_cases
    assert bean["actual_q_updates"]==episodes
    assert len(bean_trials)==episodes
    manifest=[
        sha({"regime":lab.workload(holdout_seed,e)[0],
             "jobs":[asdict(j) for j in lab.workload(holdout_seed,e)[1]]})
        for e in range(holdout_cases)]
    assert sha(manifest)==own["case_dataset_sha256"],"holdout source mismatch"
    import gzip
    full={"bean_trials":bean_trials,
          "feedback_events":feedback.events,
          "frozen_policy":summary["policy"]}
    raw=lab.canonical(full)
    packed=gzip.compress(raw,compresslevel=9,mtime=0)
    if gzip.decompress(packed)!=raw:
        raise AssertionError("compression recovery")
    (out/"all_training_events.json.gz").write_bytes(packed)
    result={"schema":SCHEMA,"seed":seed,"training_cases":episodes,
            "holdout_cases":holdout_cases,
            "BEAN_real_Q_updates":bean["actual_q_updates"],
            "BEAN_ledger":bean["ledger_verify"],
            "feedback_mutations":summary["reflections"],
            "feedback_ledger_tip":summary["ledger_tip"],
            "engines":{"BEAN":"BEAN Core PortfolioLedger TD-Q",
                       "comparator":"Custom GEPA-inspired diagnostic feedback policy mutation",
                       "official_GEPA_executed":False,
                       "OpenHands_executed":False,
                       "language_model_invocations":0},
            "holdout":{"BEAN_Q_mean_cost":own["mean_cost"]["bean_q"],
                       "diagnostic_mutation_mean_cost":alternative["mean_cost"],
                       "FIFO_mean_cost":own["mean_cost"]["fifo"],
                       "best_fixed_rule_mean_cost":min(
                           own["mean_cost"][a] for a in lab.ACTIONS),
                       "per_case_oracle_mean_cost":own["mean_cost"]["per_case_oracle"],
                       "fixture_sha256":own["case_dataset_sha256"],
                       "mutation_replay_sha256":alternative["replay_sha256"],
                       "mutation_decisions":alternative["decision_counts"]},
            "archive":{"sha256":hashlib.sha256(packed).hexdigest(),
                       "original_sha256":hashlib.sha256(raw).hexdigest(),
                       "size_bytes":len(packed),"source_bytes":len(raw),
                       "exact_recovery":True},
            "limitations":[
                "Simulation only, not real manufacturing work orders",
                "Comparator imitates test-feedback policy mutation, not official GEPA",
                "OpenHands requires a separate real coding-agent task benchmark",
                "All policies select from four predefined dispatch rules"]}
    (out/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    return result


def run(out_dir,*,seeds=(1093,2003,3019),episodes=3000,holdout_cases=400):
    out_dir=Path(out_dir)
    scores=[]
    for seed in seeds:
        scores.append(one_seed(out_dir/str(seed),seed,episodes,holdout_cases))
    avg={}
    for key in ("BEAN_Q_mean_cost","diagnostic_mutation_mean_cost",
                "FIFO_mean_cost","best_fixed_rule_mean_cost","per_case_oracle_mean_cost"):
        avg[key]=round(sum(s["holdout"][key] for s in scores)/len(scores),6)
    winners=[("BEAN" if s["holdout"]["BEAN_Q_mean_cost"]<
                        s["holdout"]["diagnostic_mutation_mean_cost"] else
              "feedback" if s["holdout"]["BEAN_Q_mean_cost"]>
                            s["holdout"]["diagnostic_mutation_mean_cost"] else
              "tie") for s in scores]
    report={"schema":SCHEMA,"actual_openhands_runs":0,
            "actual_gepa_runs":0,
            "language_model_calls":0,
            "total_BEAN_Q_updates":len(seeds)*episodes,
            "total_feedback_training_cases":len(seeds)*episodes,
            "seeds":list(seeds),"per_seed":scores,
            "holdout_mean_cost_across_seeds":avg,
            "per_seed_winner":winners,
            "note":"Only BEAN vs a model-free GEPA-inspired comparator; no official-agent standings."}
    out_dir.mkdir(parents=True,exist_ok=True)
    (out_dir/"comparison.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    return report
