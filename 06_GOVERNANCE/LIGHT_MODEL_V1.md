# LIGHT MODEL V1 - Optimization Specification

Status: CURRENT / APPROVED
Decision authority: Andrea
Governance decisions: D57, D58, D59, D69-D90, D96-D99, D102, D104-D107, D111-D112
Branch: thesis
Date: 2026-10-23

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
- Under D102, no new LIGHT infrastructure may be located on any OSM edge with `highway=motorway` or `highway=motorway_link`. This is a location-only exclusion: motorway and motorway_link remain traversable in routing under the governed directed network and turn restrictions. Existing/PUN capacities are not deleted or reclassified by D102.
- Under D111, an off-mainline TEN-T candidate location on a directed corridor requires governed exit A and governed re-entry B, with two **independent directional** driving-distance limits: `d_B5(A, location) <= 3 km` and `d_B5(location, B) <= 3 km`. An aggregate detour <= 3 km is neither required nor a substitute for checking each leg separately. B may be A or a distinct source-first access_group downstream on the same TEN-T corridor and in the same travel direction. The complete route must be B5-valid: no U-turn, opposite-carriageway/direction return or upstream re-entry. Under D104-D106, local intermediate movement on another axis is not automatically disqualifying when the final continuation/re-entry respects the original corridor and direction.
- For the FVG-internal AFIR contract, consecutive active/fixed opportunities remain subject to the D80 60 km rule with the governed road access legs. D111 does not change D102 candidate-location exclusions or qualify any previously reviewed location automatically.
- AFIR 2030 pool power is hard: on TEN-T Core, each direction requires at least 600 kW per pool and at least two recharging points of at least 150 kW each; on TEN-T Comprehensive, each direction requires at least 300 kW per pool and at least one recharging point of at least 150 kW (D81).
- AFIR pool micro-siting is an execution-level requirement (D84): when multiple new D51/D82 stations are marked as one AFIR pool, they must ultimately be realized in the same physically identifiable AFIR specific location. MODEL V1 does not choose parcel/parking-bay geometry. Same TEN-T exit or mere proximity is not sufficient by itself to establish one pool; existing PUN are not artificially grouped.

D99 clarifies the AFIR activation contract for the first diagnostic Phase I: qualified AFIR access_groups are optional opportunities rather than mandatory individual activations. The solver may select a subset, while consecutive active/fixed pools in the same direction must satisfy the D80 60 km rule inside the governed FVG scope. Pool power remains governed by D81; existing validated capacity may contribute only when attributable to the same specific pool under D84, and new D51 units cover only the residual deficit. No fictitious boundary pools or anchors are allowed. D105 subsequently removes foreign PUN, foreign AFIR pools/compliance and the foreign-side 60 km check from MODEL V1: those items are OUT_OF_SCOPE_BY_ASSUMPTION rather than a pending boundary certificate. D104-D106 retain only the border topology/direction requirement needed to prove valid same-direction, non-upstream continuation/re-entry.

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

Assignment to an edge alone does not automatically cover every path traversing that edge. For ordinary non-TEN-T siting, the selected physical realization must be traversed by the canonical path. For TEN-T off-mainline siting, D78-D80 and D111 govern the exception through a direction-compatible TEN-T exit A, candidate location and re-entry B. The two directional access legs are assessed independently for D111 eligibility, and the applicable access distances remain part of D80's governed longitudinal AFIR accounting. The canonical OD paths remain FROZEN; this does not authorize rerouting.

## 6. Phase I - feasibility

First solve the decision problem:

Does there exist a configuration of exactly 611 new infrastructures, allocated to directed topological edges, that satisfies every hard constraint?

At minimum:

g_p <= 100 km for every p in P+

Other hard constraints are enforced according to their approved contracts, including D50, D59, D69-D85, D99, D102, D104-D107, D111 and D112. In particular, B3 territorial coverage is a hard constraint for all 215 FVG municipalities under D74-D77; new infrastructure realizations are restricted to the FVG perimeter under D76; AFIR TEN-T remains a hard overlapping constraint inside the governed FVG scope under D78-D81; D102 governs candidate-location eligibility; D104-D106 govern border continuation/re-entry directionality; D107/D112 govern the TEN-T directed edge-membership and longitudinal-continuity preprocessing; and D111 governs both independent 3 km directional access/re-entry legs for off-mainline TEN-T candidate eligibility.

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

## 9. Computational architecture - B6-A APPROVED / B6-B CLOSED/PASS

D87 approves the B6-A architecture for the first diagnostic Phase I run:
- discrete MILP master on `edge_id` / `n_e`, with `sum_e n_e = 611`;
- B3 and the finite AFIR contract represented upfront after deterministic preprocessing;
- LIGHT 100 km path-gap constraints handled by outer row generation rather than full upfront materialization;
- D85 Selective Exact Expansion preserved: continuous witnesses appear only for `LOCATION_SENSITIVE` instances;
- common geometric feasibility, including D50, is checked by a logic-based geometry oracle that may return only logically justified conflict/no-good cuts.

B6-B is CLOSED/PASS for its historically verified candidate universe, PUN/B3/AFIR mapping and backend benchmark. That PASS does not certify global D107/D111/D112 implementation or Phase I readiness. Under D97, HiGHS/highspy is the approved primary backend for the first diagnostic Phase I; SCIP/PySCIPOpt remains the comparison/fallback backend. Google Colab is an allowed alternate execution environment when moving computation off the laptop is advantageous. D97 does not change the D87 architecture. Under D99, the diagnostic AFIR master selects among qualified opportunities rather than activating all of them and applies residual pool-power requirements after valid existing contribution inside the governed FVG scope. Under D105, foreign PUN/pools/AFIR compliance and foreign-side 60 km verification are OUT_OF_SCOPE_BY_ASSUMPTION; D104-D106 retain the local border topology/direction checks, now closed with `BORDER_DIRECTIONAL_CONSISTENCY_READY=YES`.

PHASE_I_RUN_READY remains NO until the diagnostic Phase I run gate is defined and verified.

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

D89-D90 define the source-first AFIR evidence contract: official/governed access identity comes first, then FROZEN-graph verification. D102 supersedes D96 on candidate-location scope: all motorway and motorway_link edges are excluded as new locations, while remaining traversable for access/re-entry routing.

The historical AFIR evidence gate is PASS under D89-D90 and B6-B is PASS within the perimeter then verified. B3 contribution remains separate D74/D77 preprocessing. D102 fixes current candidate eligibility; D97 selects HiGHS/highspy as the primary backend for the first diagnostic Phase I, with SCIP as fallback/comparison and Colab allowed as an alternate execution environment. `TEN_T_3KM_ELIGIBILITY_READY=YES` and `BORDER_DIRECTIONAL_CONSISTENCY_READY=YES` refer to historical local D102/D104-D106 checks, not global certification of D107 directed membership, D111's independent two-leg 3 km requirements or D112 connector classification. `PHASE_I_RUN_READY = NO`.

### 9.2 AFIR access identity, candidate eligibility and border-direction contract - D89/D90/D99/D102/D104-D106

D89 makes AFIR access-group identity source-first: official/governed source identity first, then FROZEN-graph verification of ramps and direction. D90 permits source-supported, graph-verified service-area or parking-area accesses in the AFIR evidence mapping. D102 excludes `motorway` and `motorway_link` only from new-location eligibility and preserves their routing traversability. D99 retains the first-diagnostic activation rule: qualified access_groups are opportunities, not mandatory activations; active/fixed pools inside the governed FVG scope satisfy D80/D81 and validated existing capacity may contribute only under D84. D104 allows the immediate transborder continuation of the same corridor as the local same-direction target where the national road name changes; RA14 FORWARD -> A3 FORWARD is the verified case. D105 requires final re-entry/continuation to be same-direction and non-upstream relative to the original TEN-T corridor, and places foreign PUN/pools/AFIR/60 km outside MODEL V1 by assumption. D106 clarifies that intermediate travel on another axis does not violate D105 if the B5-valid path finally rejoins the original corridor same-direction and non-upstream. The border audit closed 11/11 cases; the two formerly UNKNOWN cases were resolved as B5-valid re-entry existence checks: A4 Latisana REVERSE `132561 -> 460202` (6.63 km) and RA13 Fernetti REVERSE `1666798 -> 39903` (5.99 km). These two existence checks do not certify individual candidate locations within 3 km. RA14 Fernetti FORWARD independently confirmed 416/527 D102 outbound candidates satisfying both local 3 km legs under D104. The 110 raw transitions remain diagnostic evidence only and are not assumed to be a complete exit set.

### 9.3 Governed TEN-T directed membership and off-mainline two-leg eligibility - D107/D111/D112

**D107 - route-level TEN-T to B5 edge membership (APPROVED contract, not a global PASS).** Use the validated official FVG TENtec route-level crosswalk as corridor authority and the FROZEN OSM/B5 network as physical authority. Directed classification must jointly consider OSM `ref` and `name` (never `ref` alone), `highway` for mainline/link distinction, `way_id`, topological continuity through `u/v`, and graph direction. Previously audited TEN-T accesses are anchors for source/graph QA. One governed corridor can traverse multiple OSM road references (e.g. A/SS202) when official identity and topology justify continuity. Target output: `edge_id -> axis -> direction -> membership_type` with provenance. Flag unresolved edge identities, discontinuities and directional ambiguities to the CURRENT Madre rather than inferring a membership automatically. TEN-T membership is independent of eligibility for a new location under D102.

**D112 - longitudinal link through a toll/interchange complex (APPROVED contract).** A B5 edge with `highway=motorway_link` or `highway=trunk_link` may be `LONGITUDINAL_CONNECTOR` only when the governed route-level crosswalk, directed B5 topology, corridor direction and available source/visual QA jointly establish longitudinal TEN-T through movement rather than an ordinary exit/re-entry branch. Such membership carries corridor continuity for D107 and D80 while retaining the original OSM/B5 highway class; `highway=link` alone never establishes this role. Andrea approved A4 Monfalcone Est/Lisert FORWARD `289903 -> 289904 -> 289857` and REVERSE `1688252 -> 1688258` as longitudinal movements. Prior component-level association of edge `289903` as an exit does not override the verified edge-level movement. The separate governed source-first identity remains `A4::Monfalcone Est`; neither access_group identities nor D89-D90 qualification are merged or redefined. D102 remains unchanged: `motorway` and `motorway_link` are traversable where B5 permits but cannot host new candidate locations. Monfalcone's approved result is not an automatic classification of other complexes.

**D111 - two independent directional 3 km legs (APPROVED contract).** For each TEN-T off-mainline candidate location, prove a governed exit A and governed re-entry B: `d_B5(A, location) <= 3 km` **and independently** `d_B5(location, B) <= 3 km`. Do not replace either limit by a single total-detour threshold. B may be A or a separate, downstream governed access_group of the same TEN-T corridor in the same direction. The complete route must be B5-valid, without U-turn, opposite-carriageway/direction return or upstream re-entry. Where A and B differ, their D89-D90 source-first identities stay distinct: access_group identity/qualification and candidate-route eligibility are separate checks. Previously excluded cases based solely on requiring exit and re-entry within one access_group (including H-113/H-115/H-151) require individual re-examination, not automatic qualification or promotion.

**Scope of checks and outstanding scientific QA:**
- Historical `TEN_T_3KM_ELIGIBILITY_READY=YES`, `BORDER_DIRECTIONAL_CONSISTENCY_READY=YES` (11/11 in the historical border audit), B6-B PASS, and PUN/AFIR evidence PASS/READY apply only to the rules, objects and evidence actually checked. The two historical B5-valid re-entry existence witnesses and the RA14 Fernetti FORWARD case-specific two-leg screening in §9.2 are not a global D111 certificate.
- Directed TEN-T membership v03 and D112 classification are not globally certified: `D107_V03 = NOT_READY`. Lacotisce REVERSE exit versus `LONGITUDINAL_CONNECTOR` remains `NON_CONFERMATO` pending governed directional evidence; do not generalize the approved Monfalcone case.
- Global D111 two-leg 3 km testing remains `NOT_TESTED`; `B_SOURCE_FIRST_GLOBAL = NOT_READY` and 11 access reviews remain formally `OPEN`. Neither existing source-first access_group qualification nor older PASS/READY certifies a new candidate location.
- D105 retains the applicable *local* cross-border same-direction/non-upstream continuation/re-entry checks, while foreign PUN, foreign AFIR pools/compliance and foreign-side 60 km gaps are `OUT_OF_SCOPE_BY_ASSUMPTION`, not an external AFIR gate to close later.
- ISS-002 and ISS-004 remain `OPEN`; `PHASE_I_RUN_READY = NO`. No new scientific run, automatic edge/location promotion, FROZEN change or methodological approval follows from this documentation synchronization.

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
4. B6-B = CLOSED / PASS: real solver-ready candidate universe and PUN/B3/AFIR mappings verified; backend benchmark completed;
5. solver/backend = APPROVED / D97: HiGHS/highspy primary, SCIP fallback/comparison; Colab allowed as alternate execution environment;
6. AFIR activation contract = APPROVED / D99 for the governed FVG scope: qualified access_groups optional, residual pool-power logic, no fictitious anchors;
7. candidate/border contract = APPROVED / D102 + D104-D106: motorway/motorway_link excluded only as new locations, historical local TEN-T 3 km eligibility READY and border directional consistency READY 11/11, foreign PUN/pools/AFIR/60 km OUT_OF_SCOPE_BY_ASSUMPTION;
8. D107/D111/D112 = APPROVED semantic contracts but newly required global scientific QA remains OPEN: D107_V03 NOT_READY, D111 double-leg NOT_TESTED, B_SOURCE_FIRST_GLOBAL NOT_READY, 11 access reviews OPEN; case-specific Monfalcone D112 classification is APPROVED, Lacotisce remains NON_CONFERMATO, no automatic candidate promotion;
9. define and verify the diagnostic Phase I run gate, including closure of the applicable newly introduced D107/D111/D112 scientific checks; PHASE_I_RUN_READY = NO;
10. run the first diagnostic Phase I feasibility with exactly 611 only after that gate is approved;
11. reassess ISS-003 after the first Phase I result and before canonical/final LIGHT promotion;
12. if feasible and governance gates are satisfied, continue with Phase II-A and Phase II-B.

No corrective deployment rerun or canonical promotion occurs before these gates are closed.