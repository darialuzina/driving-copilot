# CBR Self-Reflection and Independent Driving

> Source: CBR, Rijprocedure personenauto (B), versie juli 2026, Inleiding and §3.
> URL: https://www.cbr.nl/nl/voor-rijscholen/nl/rijprocedures/rijprocedure-b-1

## Why self-reflection is part of the training

The high accident risk for beginning drivers led the ministry to require that they be
better prepared for daily practice. The **GDE matrix** speaks of *higher-order skills*
(hogere orde vaardigheden). By paying attention during the lessons to **independent
driving with a navigation system** and to **zelfreflectie** (self-reflection), the
candidate is better able to meet the demands of current traffic. (Rijprocedure B,
Inleiding.)

## Independent driving on the exam

Independent driving (zelfstandig rijden) is one of the exam parts (Rijprocedure B, §3,
under the CBR competency matrix). The skills matrix tracks it under:

- **Navigation-led driving** (navigatie) — following a route given by a navigation
  system.
- **Route signs** (borden volgen) — following directional signs to a destination.
- **Cluster assignments** (clusterritten) — driving a cluster of destination
  directions.

The examiner wants to see that the candidate can drive a route independently, make
their own well-founded choices, and adjust when the situation changes — without the
examiner having to guide every step.

## Self-reflection as a higher-order skill

The Rijprocedure encourages the candidate to look at their own driving critically,
both during training and afterwards. For the licence holder, the Rijprocedure is a
complete reference work to critically review their own driving skill. Concretely,
self-reflection means:

- Recognising one's own weak and strong skills and practising the weak ones.
- After a lesson, noting what went well and what needs attention (this is exactly
  what the Driving Copilot's `log_lesson` and gap analysis support).
- Building a realistic picture of readiness before the exam.

## How the Driving Copilot maps to this

The Copilot's skills matrix and the `get_gap_analysis` / `get_skill_progress` tools
operationalise self-reflection: they derive, from Daria's own logged assessments,
which skills are `weak`, `solid`, `in_progress`, or `not_started`, and which solid
skills have gone `stale` (not practised in 21+ days) and need a refresh. These
definitions live in code (spec section 3) and are the only definitions of those words
in the system.

See also: `exam_structure` for how independent driving fits in the exam, and
`assessment_criteria` for how the examiner weighs it.
