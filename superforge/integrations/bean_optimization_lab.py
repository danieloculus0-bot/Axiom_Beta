"""BEAN x Axiom simulated manufacturing scheduling Q-learning laboratory.

Uses BEAN Core's actual experimental PortfolioLedger TD updater. No duplicate
learner, shop database connection, employee data, or production scheduling
changes. The experiment is reproducible, and all 3,000 episode outcomes get
a durable ledger receipt plus full compressed synthetic-case evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random

# Must be supplied from a SEPARATE, pinned BEAN Core research checkout.
from bean.optimization.portfolio_ledger import PortfolioLedger

SCHEMA = "axiom.bean.q3000.v1"
APP = "Axiom_Beta/research_scheduling"
ACTIONS = ("fifo", "earliest_due", "shortest_processing", "minimize_setup")
REGIMES = ("late_sensitive", "setup_heavy", "flow_time")
TRAIN_EPISODES = 3000


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Job:
    identifier: int
    duration: int
    due: int
    family: str


def workload(seed, episode):
    """One reproducible case from an explicitly named synthetic distribution."""
    rng = random.Random((seed << 24) + episode)
    regime = REGIMES[rng.randrange(len(REGIMES))]
    jobs = []
    for index in range(8):
        jobs.append(Job(index, rng.randint(1, 10), rng.randint(12, 43),
                        rng.choice(("A", "B", "C"))))
    return regime, tuple(jobs)


def dispatch(jobs, strategy, *, regime):
    """Measure the complete schedule, including lateness, setup, flow time."""
    if strategy not in ACTIONS or regime not in REGIMES:
        raise ValueError("unknown strategy or regime")
    pending = list(jobs)
    elapsed, tardy, flow, changes = 0, 0, 0, 0
    family = "A"
    sequence = []
    while pending:
        if strategy == "fifo":
            chosen = min(pending, key=lambda x: x.identifier)
        elif strategy == "earliest_due":
            chosen = min(pending, key=lambda x: (x.due, x.identifier))
        elif strategy == "shortest_processing":
            chosen = min(pending, key=lambda x: (x.duration, x.identifier))
        else:
            chosen = min(pending, key=lambda x: (
                x.family != family, x.due, x.identifier))
        pending.remove(chosen)
        different = chosen.family != family
        changes += int(different)
        # This setup duration applies to all rules, not only the setup rule.
        elapsed += (4 if different else 0) + chosen.duration
        tardy += max(0, elapsed - chosen.due)
        flow += elapsed
        family = chosen.family
        sequence.append(chosen.identifier)
    weights = {"late_sensitive": (5.0, 0.15, 0.3),
               "setup_heavy": (0.2, 0.2, 12.0),
               "flow_time": (0.15, 3.0, 0.4)}[regime]
    cost = (weights[0] * tardy + weights[1] * flow
            + weights[2] * changes)
    return {"cost": round(cost, 6), "tardiness": tardy,
            "flow_time": flow, "setups": changes, "sequence": sequence}


def state_for(regime, jobs):
    # Context must be observable BEFORE the action.
    # Bucket captures a bit of difficulty without leaking outcome labels.
    mean = sum(j.duration for j in jobs) / len(jobs)
    load = "heavy" if mean >= 6 else "light"
    return f"dispatch/{regime}/{load}"


def policy_action(ledger, state, rng, epsilon):
    if not 0 <= epsilon <= 1:
        raise ValueError("invalid epsilon")
    values = ledger._q(APP, state)
    if rng.random() < epsilon:
        return rng.choice(ACTIONS)
    # Randomized tie breaks for exploration, but a deterministic seed.
    best = max(values.get(action, 0.0) for action in ACTIONS)
    candidates = [a for a in ACTIONS if math.isclose(
        values.get(a, 0.0),best,abs_tol=1e-12)]
    return rng.choice(candidates)


def score_case(regime,jobs,action):
    costs = {name: dispatch(jobs,name,regime=regime) for name in ACTIONS}
    chosen = costs[action]
    fifo = costs["fifo"]
    reward = (fifo["cost"] - chosen["cost"]) / max(1.0, fifo["cost"])
    return round(max(-3.0,min(3.0,reward)),10), costs


def evaluate(ledger, seed, episodes, *, random_policy_seed=1337):
    """Independent frozen evaluation: never writes to or trains from ledger."""
    rng = random.Random(random_policy_seed)
    totals = {a:0.0 for a in ACTIONS}
    totals["bean_q"] = 0.0
    totals["uniform_random"] = 0.0
    totals["per_case_oracle"] = 0.0
    decisions = {a:0 for a in ACTIONS}
    deltas = []
    fixture_refs = []
    for episode in range(episodes):
        regime,jobs=workload(seed,episode)
        st=state_for(regime,jobs)
        action=policy_action(ledger,st,rng,epsilon=0)
        costs={a: dispatch(jobs,a,regime=regime)["cost"] for a in ACTIONS}
        for a in ACTIONS:
            totals[a] += costs[a]
        totals["bean_q"] += costs[action]
        totals["uniform_random"] += sum(costs.values()) / len(ACTIONS)
        totals["per_case_oracle"] += min(costs.values())
        decisions[action] += 1
        deltas.append(costs["fifo"]-costs[action])
        fixture_refs.append(sha(canonical({"regime":regime,
                                             "jobs":[asdict(j) for j in jobs]})))
    return {"cases":episodes,"seed":seed,
            "mean_cost":{k:round(v/episodes,6) for k,v in totals.items()},
            "decision_counts":decisions,
            "mean_savings_vs_fifo":round(sum(deltas)/episodes,6),
            "case_dataset_sha256":sha(canonical(fixture_refs))}


def run_training(db_path, *, episodes=TRAIN_EPISODES, train_seed=1093,
                 validate_seed=55001, holdout_seed=99001, test_cases=400,
                 verbose_trials=False):
    """Run *real* Q-updates on 3000 newly generated, independently scored cases.

    Test/holdout is never used during action selection. The validation cases
    are observational checkpoints, not used to select hyperparameters.
    """
    if type(episodes) is not int or not 1 <= episodes <= 3000:
        raise ValueError("episodes must be between 1 and 3000")
    if len({train_seed,validate_seed,holdout_seed})!=3:
        raise ValueError("training, validation and holdout seeds must differ")
    if not 1 <= test_cases <= 2000:
        raise ValueError("invalid holdout case count")
    ledger=PortfolioLedger(db_path)
    rng=random.Random(42421 + train_seed)
    trials=[]
    checkpoints=[]
    start_verify=ledger.verify()
    if start_verify["events"]:
        raise ValueError("experiment needs an empty isolated SQLite ledger")
    before=evaluate(ledger,validate_seed,test_cases)
    try:
        for episode in range(episodes):
            regime,jobs=workload(train_seed,episode)
            state=state_for(regime,jobs)
            # Gradual exploration decline; the reward comes from independent
            # scheduling cost, not BEAN's own explanation or test count.
            epsilon = 0.26-0.22 * episode/max(1,episodes-1)
            action=policy_action(ledger,state,rng,epsilon)
            reward, outcomes=score_case(regime,jobs,action)
            fixture={"episode":episode,"regime":regime,
                     "jobs":[asdict(j) for j in jobs],
                     "state":state,"chosen":action,
                     "reward":reward,"outcomes":outcomes}
            input_sha=sha(canonical(fixture))
            evidence_ref=f"synthetic://axiom/scheduling/{input_sha[:32]}"
            res=ledger.observe(app=APP,event_id=f"episode_{episode:06d}",
                               state=state,action=action,
                               reward=reward,next_state=None,done=True,
                               kind="synthetic",evidence_ref=evidence_ref,
                               revision=SCHEMA,
                               tags=("scheduling","simulation"))
            if not res["new"]:
                raise AssertionError("expected a new, unique experience")
            fixture["event_receipt"]=res["receipt"]
            trials.append(fixture)
            if (episode+1) in set([250,500,1000,1500,2000,2500,episodes]):
                valid=evaluate(ledger,validate_seed,test_cases)
                checkpoints.append({
                    "at_episode":episode+1,
                    "validation":valid,
                    "ledger_tip":res["receipt"]})
        final=ledger.verify()
        # Independent cold holdout: first access occurs ONLY after
        # all training and intermediate validation is finished.
        heldout=evaluate(ledger,holdout_seed,test_cases)
        original=ledger.event(APP, "episode_000000")
        last=ledger.event(APP,f"episode_{episodes-1:06d}")
        if not original or not last:
            raise AssertionError("missing source-level event recovery")
        if final["events"]!=episodes or final["rewarded_events"]!=episodes:
            raise AssertionError("Q ledger lost a scored learning episode")
        scoreboard=ledger.portfolio_context()
        report={"schema":SCHEMA,"training_episodes":episodes,
                "actual_q_updates":final["rewarded_events"],
                "dataset":"synthetic_measured_simulated_shop_scheduling",
                "model":"BEAN PortfolioLedger tabular terminal-state TD Q-learning",
                "gamma_behavior":"terminal episodes, so TD future term is 0",
                "train_seed":train_seed,"validation_seed":validate_seed,
                "holdout_seed":holdout_seed,
                "pretraining_validation":before,
                "validation_checkpoints":checkpoints,
                "independent_holdout":heldout,
                "ledger_verify":final,"portfolio_scoreboard":scoreboard,
                "full_episode_evidence_sha256":sha(canonical(trials)),
                "source_evidence_rows":len(trials),
                "trials":trials if verbose_trials else None}
        return report, trials
    finally:
        ledger.close()
