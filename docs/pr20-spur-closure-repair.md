# PR20 spur-closure repair (historical)

PR20 introduced a separate bounded post-processing lane for GraphHopper-routed
downstream spur connectors. It established the core invariants that connector
geometry must be graph-valid, physical edge identity—not coordinate proximity—must
drive reuse checks, exact and deliberate anchors must remain authoritative, repair
failure must be nonfatal, and originals must remain publishable.

PR21 removed that independent full-candidate search. Spur reconnection is now one
sparse neighborhood inside the shared edge-aware complete-tour optimizer, using the
same request cache and the single typed `global_optimization` budget. Structural
dominance remains a publication rule after shared final evaluation.

See
[`pr21-soft-stop-local-optimization.md`](pr21-soft-stop-local-optimization.md) for
the current architecture, budgets, diagnostics, browser behavior, and limitations.
