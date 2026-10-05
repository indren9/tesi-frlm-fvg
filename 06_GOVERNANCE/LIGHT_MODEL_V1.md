# LIGHT MODEL V1 - Optimization Specification

Status: CURRENT / APPROVED
Decision authority: Andrea
Governance decisions: D57, D58, D59, D69-D90
Branch: thesis
Date: 2026-10-01

## 1. Purpose

MODEL V1 is the current LIGHT optimization model for allocating the 611 new charging infrastructures fixed by D51-D53.

The approved elementary planning unit is one directed topological edge of the frozen LIGHT OSM network.

Technical identity:
edge_id

Human-readable/classifying attributes:
(comune, arteria, direzione)

The physical point is not the planning unit. Geometry is auxiliary and is used only to verify that an edge-level allocation can be physically realized under the hard constraints.

## 2. Fixed baseline

MODEL V1 does not reopen the following:
- N_new = 611.
- Each new infrastructure remains a 150 kW-total recharging station with 2 charging points (D51). Under D82, those two points are treated as two AFIR recharging points, each with individual power output >=150 kW, while the station total power output remains 150 kW shared; simultaneous 150+150 kW delivery is not required.
- Maximum 4 new infrastructures co-located at one physical point (D83, superseding D38).
- Canonical LIGHT OD/path system is FROZEN; no rerouting.
- Only paths with path_flow_veh_day > 0 enter the longitudinal 100 km constraint (D43).
- Minimum separation between distinct physical positions involving new infrastructure is 1,000 m Euclidean (D50).
- Elementary planning unit = one directed topological edge, identified canonically by edge_id (D59).
- segment_uid identifies the underlying physical segment and must not collapse directional identity when direction matters.
- comune, arteria and direzione classify the edge; they do not define a larger multi-edge planning unit.
- A physical realization must lie on the geometry of the selected edge (D59).
- A facility contributes to a path only if that canonical path actually traverses its physical realization (D59, preserving the D48 principle).
- Existing infrastructure is fixed and is not moved or artificially grouped.
- PUN power accounting follows D40-D42. For the longitudinal 100 km gap, only the 61 PUN locations validated under D70-D73 may contribute; the 29 unresolved locations remain in power accounting but do not interrupt path gaps.
- Territorial coverage B3 applies to all 215 FVG municipalities (D75). For municipality c, coverage uses the minimum physical network distance from its three frozen Gamma_OSM accesses: d_c(x) = min_{a in Gamma_c} d_G(a,x), with a 10 km threshold (D74). This is separate preprocessing on the frozen LIGHT network and does not reroute canonical OD paths.
- Existing PUN territorial contribution follows D77: the 61 validated positions may satisfy B3; the other 29 positions do not count for B3.
- New infrastructure may be physically realized only inside the Friuli Venezia Giulia perimeter (D76). An edge wholly outside FVG is ineligible; for an edge crossing the regional boundary, only its internal portion is admissible and the physical witness must lie on that portion.
- On motorway TEN-T mainline arcs no new LIGHT infrastructure is placed. TEN-T charging opportunities are realized off-mainline through direction-compatible TEN-T exits (D78-D80).
- An off-mainline TEN-T charging opportunity must be within 3 km driving distance from the pertinent TEN-T exit. AFIR is a hard overlapping constraint on TEN-T: consecutive AFIR opportunities are limited to 60 km, using the operational road distance including both access legs and the TEN-T section between exits (D80).
- AFIR 2030 pool power is hard: on TEN-T Core, each direction requires at least 600 kW per pool and at least two recharging points of at least 150 kW each; on TEN-T Comprehensive, each direction requires at least 300 kW per pool and at least one recharging point of at least 150 kW (D81).
- AFIR pool micro-siting is an execution-level requirement (D84): when multiple new D51/D82 stations are marked as one AFIR pool, they must ultimately be realized in the same physically identifiable AFIR specific location. MODEL V1 does not choose parcel/parking-bay geometry. Same TEN-T exit or mere proximity is not sufficient by itself to establish one pool; existing PUN are not artificially grouped.

D59 supersedes D46-D48 and amends D57 only on the definition of the planning unit. The feasibility/minimax/traffic-weighted structure of D57 remains current.

## 3. Planning decision

For each directed topological edge e:

n_e = number of new infrastructures assigned to edge e

Subject to:

sum_e n_e = 611

All 611 new infrastructures remain reallocatable during optimization. They are not inserted greedily and frozen one by one.

For reporting, a selected unit may be exposed as readable attributes such as comune + edge_id + direzione, while edge_id remains the canonical decision identity. Where 2 or 4 new stations are assigned to satisfy one AFIR pool, the optimization marks them as belonging to one pool; the exact common specific location is deferred to execution under D84.

An edge is not automatically one physical point. If n_e > 1, one or more physical realizations on that edge may be required. Every physical point remains subject to the D83 cap of at most 4 new infrastructures, and distinct relevant physical positions remain subject to D50.

### 3.1 B5 physical realization encoding — CLOSED / D85

B5 adopts an adapted Heavy D34 Selective Exact Expansion principle.

- `edge_id` and `n_e` remain the canonical planning decisions.
- No universal continuous coordinate, metric grid, sampling lattice or manually selected candidate point is introduced.
- Each hard-constraint instance is screened on the admissible edge geometry with exact min/max bounds and classified as `ROBUST_COMPATIBLE`, `INCOMPATIBLE` or `LOCATION_SENSITIVE`.
- Only `LOCATION_SENSITIVE` instances activate a continuous physical witness.
- The same witness must satisfy all applicable hard constraints simultaneously.
- One witness may host 1–4 new stations under D83.
- If `n_e > 4`, or feasibility genuinely requires more than one physical point on the same edge, multiple witnesses are allowed; each hosts at most 4 stations and distinct witnesses must satisfy D50 and all other geographic/directional gates.
- Witness coordinates are mathematical feasibility certificates only, not executive construction locations; D84 remains controlling for AFIR micro-siting.

The exact variable implementation, linearizations and constraint-generation mechanics belong to B6 and may not change this B5 semantic contract.

## 4. Edge identity and future aggregation

Primary technical key:
edge_id

Supporting physical-segment key:
segment_uid

Readable attributes may include:
- comune;
- arteria;
- direzione;
- optional progressive/kilometric description.

Progressive/kilometric information is descriptive and is not the primary identity of the planning unit.

Current MODEL V1 does not aggregate multiple edges into one planning unit.

A future aggregation of consecutive edges is allowed only as a model-reduction proposal and requires:
1. proof/check that the aggregation preserves the relevant path/sub-path relationships and hard constraints;
2. explicit Andrea approval before it becomes current methodology.

## 5. Path gap

For every canonical positive-flow path p:

g_p = maximum longitudinal interval without a valid charging opportunity along p

Under D69, the interval is evaluated on the full canonical origin-to-destination path, including origin -> first charging opportunity and last charging opportunity -> destination.

The gap is a property of the ordered canonical path. It is not one OSM edge and it is not a customer-to-facility distance.

Because the planning unit is one edge, the first computational mapping is direct in identity but still path-dependent:

edge_id
-> canonical paths traversing that edge
-> position/order of that edge within each path
-> admissible physical realization on the edge
-> longitudinal contribution to the path gap

Assignment to an edge alone does not automatically cover every path traversing that edge. For ordinary non-TEN-T siting, the selected physical realization must be traversed by the canonical path. For TEN-T off-mainline siting, D78-D80 define the exception: the canonical path must traverse the direction-compatible exit relation, and the longitudinal distance includes the road access leg between exit and station.

## 6. Phase I - feasibility

First solve the decision problem:

Does there exist a configuration of exactly 611 new infrastructures, allocated to directed topological edges, that satisfies every hard constraint?

At minimum:

g_p <= 100 km for every p in P+

Other hard constraints are enforced according to their approved contracts, including D50, D59, D69-D85. In particular, B3 territorial coverage is a hard constraint for all 215 FVG municipalities under D74-D77; new infrastructure realizations are restricted to the FVG perimeter under D76; and AFIR TEN-T is a hard overlapping constraint under D78-D80.

No feasible starting solution is required. The solver/search may reallocate any of the 611 new infrastructures until feasibility is found.

If Phase I is infeasible, optimization stops and the blocking constraint set must be diagnosed before any methodology change.

## 7. Phase II-A - minimax fairness

Among all feasible configurations:

G* = min(max_p g_p)

Meaning:
1. for each candidate configuration, find its worst path gap;
2. among those worst gaps, choose the smallest possible value.

G* is the best achievable upper bound on every path maximum gap under the fixed cardinality and hard constraints.

## 8. Phase II-B - traffic-weighted refinement

Fix the Phase II-A optimum:

g_p <= G* for every p in P+

Then minimize:

sum_p f_p * g_p

where:

f_p = path_flow_veh_day

The second stage may accept a larger gap on a lower-flow path in exchange for a smaller gap on a higher-flow path only while every path remains at or below G*.

Traffic therefore refines the solution after fairness; it cannot sacrifice any path beyond the G* ceiling.

## 9. Computational architecture - B6-A APPROVED / B6-B OPEN

D87 approves the B6-A architecture for the first diagnostic Phase I run:
- discrete MILP master on `edge_id` / `n_e`, with `sum_e n_e = 611`;
- B3 and the finite AFIR contract represented upfront after deterministic preprocessing;
- LIGHT 100 km path-gap constraints handled by outer row generation rather than full upfront materialization;
- D85 Selective Exact Expansion preserved: continuous witnesses appear only for `LOCATION_SENSITIVE` instances;
- common geometric feasibility, including D50, is checked by a logic-based geometry oracle that may return only logically justified conflict/no-good cuts.

The solver/backend is deliberately NOT selected by D87. HiGHS/highspy remains only a technical benchmark candidate. B6-B must first materialize and verify the real candidate universe and solver-ready PUN/B3/AFIR mappings, quantify actual model size, and benchmark representative backends before Andrea selects a canonical solver.

`PHASE_I_RUN_READY` remains NO until the B6-B blockers are closed.

### 9.1 PUN-61 membership and directed offsets — CLOSED / D88

Andrea approved the exact Chat 10.15 reconstruction: 42 first-stage positions
plus 19 second-automatch positions. The second stage requires strong road
name/ref evidence within 75 m and no more than 6 m above the distance to the
physically nearest segment. D88 approves this exact membership, including the
five preserved first-stage normalization/coherence cases, not a new generic matcher.

Resolve `LIGHT_PUN61_SOLVER_READY_PACKAGE_V01` through the Artifact Register.
The CURRENT/VERIFIED package contains 61 positions / 163 EVSE and 106 directed
edge/offset relations on 93 distinct edge IDs, with manifest and QA evidence.
Only on an actual canonical occurrence of the same edge, use
`cum_start_m + edge_offset_from_start_m`; retain path_idx/edge_order for repeats.
There is no rerouting or forced snap to positive-flow paths. The 29 residual
positions / 139 EVSE remain in power accounting and outside geographic gates.
Do not double-count physical PUN power across directed relation rows.

D89-D90 add a source-first AFIR access contract: official/governed access identity comes first, then FROZEN-graph verification; official service-area/parking accesses are admissible only when direction-compatible exit/re-entry is confirmed.

This closes the exact-membership/offset blocker only. B3 contribution remains
separate D74/D77 preprocessing; AFIR qualification is not inferred. B6-B AFIR
exit grouping, directional access/re-entry and boundary opportunities remain
open. Complete A-D before any backend benchmark; `PHASE_I_RUN_READY = NO`.

### 9.2 AFIR access identity - D89/D90

D89 makes AFIR access-group identity source-first: official/governed source identity first, then FROZEN-graph verification of ramps and direction. D90 also permits official service-area or parking-area accesses when source-supported and graph-verified. The 110 raw transitions are diagnostic evidence only and are not assumed to be a complete exit set.

## 10. Geometry

Geometry is subordinate to edge-level planning.

The implementation must answer:

given the selected counts n_e, does there exist a physical realization on the selected edge geometries that satisfies the longitudinal and spatial hard constraints?

A physical coordinate may be used internally as a feasibility witness, but it does not replace edge_id as the planning unit.

D50 remains current: the 1 km separation metric is Euclidean. H-060 showed that local sparse road-distance preprocessing would be computationally feasible, but road distance is not the approved metric.

## 11. Deferred alternative - preserved, not current

H-062 preserves a possible future model:

fixed-path + fixed-cardinality + energy-aware Capacitated FRLM.

It would require a new contract:

LIGHT path flow -> EV charging demand -> station service load

It would also require new evidence or approved assumptions for vehicle classes, battery/SoC, consumption, charging behaviour, charging efficiency, effective power, power sharing, arrival profiles, service level and capacity.

This CFRLM is not MODEL V1, is not currently parameterized, and is not authorized for canonization. It is retained only for a possible future modification or extension.

## 12. Non-goals

MODEL V1 does not:
- reroute OD paths;
- reopen FROZEN routing artifacts;
- use standard maximum-captured-flow FRLM as the primary optimizer;
- use a multi-edge (comune, arteria[,direzione]) macro-unit as the elementary planning unit;
- convert the planning decision from edge_id to physical point;
- aggregate edges without a separate equivalence check and approval;
- assume a road-distance 1 km gate;
- invent PUN site grouping, simultaneous power or geographic contribution;
- select SoC/service-capacity parameters.

## 13. Current implementation gate

Current sequence:
1. B5 physical realization encoding = CLOSED / D85;
2. ISS-003 local over-clustering = DEFERRED / NOT CANCELLED under D86; it does not block B6 or the first diagnostic Phase I run;
3. B6-A computational architecture = APPROVED / D87;
4. B6-B = materialize/verify the real solver-ready candidate universe and PUN/B3/AFIR mappings, quantify actual cardinalities, then benchmark candidate backends;
5. Andrea selects the solver/backend only after B6-B evidence; no solver is canonical yet;
6. run the first diagnostic Phase I feasibility with exactly 611;
7. reassess ISS-003 after the first Phase I result and before canonical/final LIGHT promotion;
8. if feasible and governance gates are satisfied, continue with Phase II-A and Phase II-B.

No corrective deployment rerun or canonical promotion occurs before these gates are closed.