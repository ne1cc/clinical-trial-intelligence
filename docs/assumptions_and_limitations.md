# Assumptions and Limitations

## Source-inherited limitations
1. **Current-records-only API.** History exists only from this project's
   own snapshot cadence; transition metrics are zero until snapshots
   accrue. Registry-date proxies are labeled wherever used.
2. **Registry lag and inconsistency.** Sponsors update listings on their
   own schedule; statuses, enrollment counts, and dates may be stale.
3. **Partial dates.** Registry dates may be YYYY or YYYY-MM; parsed
   leniently with `*_raw` preserved. Day-level precision is not implied.
4. **Free-text facilities.** Facility names are not stable identifiers.
   Matching is normalized-text best-effort; overlap metrics inherit this
   fuzziness. 266 U.S. location rows in the current snapshot have no
   facility name and are excluded from the overlap mart only.

## Modeling assumptions
5. **Deterministic taxonomy.** Condition grouping is a version-controlled
   YAML keyword taxonomy (first-match-wins, confidence-tagged); no runtime
   LLM or external ontology. Low-confidence mappings are counted in
   `mart_data_reliability`, not hidden.
6. **Density proxy.** Recruiting-listing count stands in for competition
   pressure. It is not population-adjusted (ACS layer is on the roadmap)
   and does not observe actual enrollment competition.
7. **Segment grain.** Trials without a usable U.S. location are excluded
   from segment marts (U.S.-scope MVP); raw records are fully preserved.
8. **Score normalization.** Min-max within the scored population makes the
   score *relative to the current snapshot's segments*; scores are not
   comparable across projects or absolute over time.
9. **Percentile bands.** `low/moderate/elevated` and band thresholds are
   configurable cuts, not validated risk tiers.

## Scenario-model assumptions
10. Every ROI figure is arithmetic over user-editable assumptions in
    `config/roi_assumptions.yml` (costs, shares, cycle sizes). Nothing is
    observed; the disclaimer is embedded in every output object.

## Operational limitations
11. Single-condition MVP (Alzheimer's + related dementias via taxonomy);
    other areas require config changes and review of the taxonomy.
12. Weekly cadence is recommended, not enforced; gaps widen transition
    windows.
13. Local-first DuckDB warehouse; multi-user concurrency and cloud
    orchestration are roadmap items.
14. **Portfolio demonstration.** Real feasibility decisions require
    qualified clinical-operations review and additional data sources.
