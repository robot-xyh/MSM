---
name: project-proposal-writing
description: Write or revise evidence-based Chinese project proposals, feasibility studies, research applications, and capability-improvement reports. Use when a task requires sections on purpose and significance, domestic and international status and trends, urgent needs, concrete objectives, measurable indicators, research content, key technologies, innovations, overall technical方案 diagrams, difficulties and solutions, or data management.
---

# Project Proposal Writing

Produce a restrained Chinese engineering proposal whose claims, indicators, diagrams, and evidence can be reviewed independently.

## Workflow

1. Define the topic, application boundary, current baseline, planned capability, and evidence cutoff date.
2. Read the relevant repository reports before writing. Treat project simulation results as simulation evidence, not equipment or flight-test capability.
3. Build a source ledger before drafting section 1.2. Prefer official sources, standards, procurement records, and peer-reviewed papers. Label vendor claims and unreviewed preprints.
4. Draft with the exact section order in [proposal-outline.md](references/proposal-outline.md).
5. Express every technical indicator as target, unit, test condition, calculation method, data source, and acceptance rule.
6. Add a Chinese overall technical方案 diagram as a Word-compatible high-resolution PNG, normally at least 2400 px wide and 300 dpi. Keep data flow, decision flow, feedback flow, and safety boundaries explicit, and reference the image with a relative path.
7. Complete the data-management section with schema, lineage, access, storage, model/data versions, quality checks, backup, retention, and release rules.
8. Run the evidence and writing checks in [evidence-rules.md](references/evidence-rules.md).

## Evidence Rules

- Cite every time-sensitive equipment, policy, procurement, performance, or trend claim.
- Use sources that can be opened and verified. Never invent a title, author, date, DOI, URL, standard number, or performance value.
- Separate domestic and international status, then synthesize trends. Do not list products without analysis.
- Treat arXiv and vendor material as supplemental evidence. State when independent validation is unavailable.
- Distinguish implemented, simulated, proposed, recommended, optional, unavailable, and unverified capabilities.
- Keep a numbered reference list with source type, publication date, title, publisher, and stable URL or DOI.

## Writing Rules

- Write direct, restrained Chinese. Keep one judgment per paragraph.
- Avoid formulaic phrases, unsupported superlatives, contrast-heavy templates, and repeated summaries.
- Define an abbreviation at first use. Prefer Chinese technical terms in headings and diagrams.
- Do not expose repository paths, agent workflow, code provenance, or drafting process in the proposal body.
- Do not present simulation parameters as real equipment performance.
- Mark unsupported numerical values as recommended targets or values pending validation.
- For the MSM proposal set, consolidate section 1.3 into exactly three substantive urgent needs. In section 2.1, present exactly three key problems and three explicit objectives. Do not use tables for these items; each item must explain context, mechanism, intended capability, validation, and boundary in developed paragraphs.
- For the MSM proposal set, consolidate sections 3.1, 3.2, 3.3, and 4.2 into exactly three substantive subsections each. Do not use tables in these four sections; explain principles, implementation, verification, and boundaries in developed paragraphs.

## Acceptance Check

- Sections 1.1 through 4.3 are complete and ordered correctly.
- Section 1.3 contains exactly three developed urgent needs; section 2.1 contains exactly three developed key problems and three explicit objectives, without tables.
- Sections 3.1, 3.2, 3.3, and 4.2 each contain exactly three developed subsections and no tables.
- Section 1.2 includes domestic status, international status, trends, and auditable sources.
- Objectives map to urgent needs; research content maps to key problems; innovations map to technical work.
- Each indicator is measurable and has an acceptance method.
- The technical diagram agrees with the text and includes feedback and safety boundaries.
- The diagram can be inserted into Word directly, remains legible at page width, and contains no clipped or overlapping text.
- The data-management plan covers raw data, processed data, labels, models, logs, metrics, reports, and access control.
- Conclusions do not exceed available evidence.
