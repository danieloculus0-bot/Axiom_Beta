# Axiom AutoNest v1

**Status:** functional browser-local nesting prototype with independent placement verification; not a production-qualified CAM/postprocessor.

## Starting point

Open web/erp/autonest.html through GitHub Pages or another local HTTP static server. The Axiom ERP browser demo sidebar links to the workbench. It operates on a geometric solver, not a screenshot or a synthetic result generator. Its default example contains only fictional geometry.

## What is implemented

- Closed arbitrary polygon profiles including concave shapes, optional interior void loops and per-part quantity.
- Rotation candidates (default 0, 90, 180, 270 degrees); the solver accepts caller-configured angles.
- Twelve deterministic placement searches, comparing area, longest dimension, perimeter and ascending area order, with bottom-left, left-bottom and compact placement policies.
- Polygon intersection and containment, segment-to-segment clearance, minimum web + kerf, and border margin + half kerf.
- Independent post-solve verification of cutting contours against sheet bounds and other part outlines.
- Multiple sheets, explicit unplaced parts, net material area and full contour cut-perimeter accounting.
- ASCII DXF intake for **closed LWPOLYLINE**, including tessellated bulge arcs, and **CIRCLE** loops. A single DXF should contain one part outer loop plus holes; upload multiple files for multiple parts. All unmatched, open and unsupported entities are rejected, not ignored.
- R2000 ASCII DXF exports for each sheet, with closed CUT_OUTER and CUT_INNER LWPOLYLINE contours only.
- Explicit BEAN review-evidence JSON showing actual search alternatives, clearance settings and verification results.

## Geometry and limits

- Dimensions are supplied entirely in one unit system (inches or millimeters) with no automatic unit conversion.
- Minimum clearance between outer boundaries is minimumWeb + kerf; stock border inset is margin + kerf/2. This is conservative geometry separation, not automatic toolpath compensation.
- Interior holes are exported, but the solver **conservatively treats each outer contour as solid for placing other parts**. Hole-in-hole nesting is not supported yet.
- No common-line cuts, chain cutting, lead-ins, tabs, grain-direction restrictions, tool changes, heat/warp simulation, laser NC postprocessing or machine-specific validation.
- Kerf is used for layout spacing only. It is **not** a compensated toolpath, and the emitted DXF is raw part geometry.
- Arc bulges are linearized at a configurable chord tolerance. External DXF layers and annotations are not silently treated as cut geometry. SPLINE, ELLIPSE, LINE, ARC, INSERT and unsupported entity types require upstream conversion to closed polylines.
- This initial browser implementation caps a job at 100 part definitions, 250 total pieces and 1,000 vertices per polygon. It uses bounded heuristic candidate search, not guaranteed globally optimal combinatorial nesting.
- The preview is generated from actual placed points. SVG uses a vertical flip for display; DXF retains Cartesian coordinates.

## BEAN boundary

BEAN Core is **not** invoked from the public browser. The optimizer uses real geometry and algorithmic strategy selection but no externally connected inference. The Axiom_AutoNest_BEAN_Review.json export is structured evidence that BEAN can consume in a future approved local integration.

A future integration should use source-checked drawing hashes, job/part/revision bindings and outcome receipts before recording advice. BEAN may rank strategy candidates or request additional searches; the geometric solver must independently verify any resulting placement and never accept a text-only claim that a shape fits.

## Verification

Run: node --test web/erp/autonest.test.mjs

Tests cover sheet utilization, rotations, concave pocket use, multiple sheets, impossible outlines, voids, cross-part collisions, deterministic replay, malformed input, DXF roundtrip and bulge tessellation. GitHub Actions also runs this suite and JavaScript syntax checks.

## Next engineering increments

1. Real Job Passport/ForgeVault drawing revision and material-stock bindings, with private data remaining local.
2. Robust CAD/DXF geometry adapter for mixed LINE/ARC chains, splines, geometric healing and explicit drawing-unit verification.
3. Better polygon packing using no-fit polygons, local search and beam/annealing refinement; standardized regression benchmarks against actual nested sheet cases.
4. BEAN Core proposal/feedback adapter on the local server with immutable optimization evidence and measured cut results.
5. Controlled CAM export contract, grain/restrictions, remnant geometry, common-line options and machine-specific postprocessors.
