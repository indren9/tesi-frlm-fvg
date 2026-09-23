# LIGHT MODEL V1 - Optimization Specification

Status: CURRENT / APPROVED
Decision authority: Andrea
Governance decisions: D57, D58
Branch: thesis
Date: 2026-09-23

## 1. Purpose

MODEL V1 is the current LIGHT optimization model for allocating the 611 new charging infrastructures fixed by D51-D53.

The approved planning unit is:
u = (comune, arteria[, direzione])

The physical point is not the planning unit. Geometry is auxiliary and is used only to verify that a macro-allocation can be physically realized under the hard constraints.

## 2. Fixed baseline

MODEL V1 does not reopen the following:
- N_new = 611.
- Each new infrastructure = 150 kW total nominal power and 2 charging points.
- Maximum 3 new infrastructures co-located at one physical point (D38).
- Canonical LIGHT OD/path system is FROZEN; no rerouting.
- Only paths with path_flow_veh_day > 0 enter the longitudinal 100 km constraint (D43).
- Minimum separation between distinct physical positions involving new infrastructure is 1,000 m Euclidean (D50).
- Decision unit remains (comune, arteria[,direzione]) (D46).
- Physical realization must lie inside the admissible frozen-OSM domain of the selected macro-unit (D47).
- A facility contributes to a path only if that canonical path actually traverses its physical realization (D48).
- Existing infrastructure is fixed and is not moved or artificially grouped.
- PUN power accounting follows D40-D42. Geographic/path contribution of existing PUN is not inferred unless separately approved and verified.

## 3. Planning decision

For each macro-unit u:
n_u = number of new infrastructures assigned to u

Subject to:
sum_u n_u = 611

All 611 new infrastructures remain reallocatable during optimization. They are not inserted greedily and frozen one by one.

## 4. Path gap

For every canonical positive-flow path p:
g_p = maximum longitudinal interval without a valid charging opportunity along p

The gap is a property of the ordered canonical path. It is not one OSM arc and it is not a customer-to-facility distance.

A macro-allocation alone does not numerically determine g_p. An auxiliary geometric realization/check is required to establish where charging opportunities can occur while preserving the macro-unit as the planning decision.

## 5. Phase I - feasibility

First solve the decision problem:

Does there exist a configuration of exactly 611 new infrastructures, allocated to approved macro-units, that satisfies every hard constraint?

At minimum:
g_p <= 100 km for every p in P+

Other hard constraints are enforced according to their approved contracts, including D38, D46-D48 and D50. Territorial coverage and AFIR enter only where their LIGHT interpretation is deterministic and approved.

No feasible starting solution is required. The solver/search may reallocate any of the 611 new infrastructures until feasibility is found.

If Phase I is infeasible, optimization stops and the blocking constraint set must be diagnosed before any methodology change.

## 6. Phase II-A - minimax fairness

Among all feasible configurations:
G* = min(max_p g_p)

Meaning:
1. for each candidate configuration, find its worst path gap;
2. among those worst gaps, choose the smallest possible value.

G* is the best achievable upper bound on every path maximum gap under the fixed cardinality and hard constraints.

## 7. Phase II-B - traffic-weighted refinement

Fix the Phase II-A optimum:
g_p <= G* for every p in P+

Then minimize:
sum_p f_p * g_p

where:
f_p = path_flow_veh_day

The second stage may accept a larger gap on a lower-flow path in exchange for a smaller gap on a higher-flow path only while every path remains at or below G*.

Traffic therefore refines the solution after fairness; it cannot sacrifice any path beyond the G* ceiling.

## 8. Computational architecture - open

The mathematical objective and sequencing are approved. The exact solver architecture is not yet canonized.

H-061 identifies relevant families:
- full-cover path/sub-path covering;
- fixed-threshold covering with constraint/row generation;
- Branch-and-Cut with dynamic separation;
- Benders decomposition;
- Logic-Based Benders for macro-allocation versus geometric feasibility.

Because the canonical path set is large, MODEL V1 must not assume that every path/sub-path constraint must be materialized at initialization. Constraint generation/separation is a candidate implementation principle, not yet a project decision.

## 9. Geometry

Geometry is subordinate to macro-allocation.

The implementation must answer:
given the selected counts n_u, does there exist a physical realization inside the admissible portions of the selected macro-units that satisfies the longitudinal and spatial hard constraints?

A physical coordinate may be used internally as a feasibility witness, but it does not replace (comune, arteria[,direzione]) as the planning unit.

D50 remains current: the 1 km separation metric is Euclidean. H-060 showed that local sparse road-distance preprocessing would be computationally feasible, but road distance is not the approved metric.

## 10. Deferred alternative - preserved, not current

H-062 preserves a possible future model:
fixed-path + fixed-cardinality + energy-aware Capacitated FRLM.

It would require a new contract:
LIGHT path flow -> EV charging demand -> station service load

It would also require new evidence or approved assumptions for vehicle classes, battery/SoC, consumption, charging behaviour, charging efficiency, effective power, power sharing, arrival profiles, service level and capacity.

This CFRLM is not MODEL V1, is not currently parameterized, and is not authorized for canonization. It is retained only for a possible future modification or extension.

## 11. Non-goals

MODEL V1 does not:
- reroute OD paths;
- reopen FROZEN routing artifacts;
- use standard maximum-captured-flow FRLM as the primary optimizer;
- convert the planning decision from macro-unit to physical point;
- assume a road-distance 1 km gate;
- invent PUN site grouping, simultaneous power or geographic contribution;
- select SoC/service-capacity parameters.

## 12. Current implementation gate

Next work:
1. define the computational mapping macro-unit -> path/sub-path longitudinal coverage;
2. test Phase I feasibility with exactly 611;
3. define the dynamic constraint/cut strategy;
4. define the auxiliary geometric feasibility check;
5. close remaining deterministic LIGHT contracts for territorial/AFIR constraints.

No corrective deployment rerun or canonical promotion occurs before these gates are closed.
