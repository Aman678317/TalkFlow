# TalkFlow Translation Quality Metrics & Taxonomy

## 1. Dimensional Scoring Model
Every translation candidate receives an overall composite score $S \in [0.0, 1.0]$ computed from five calibrated dimensions:

$$S_{\text{raw}} = w_{\text{sem}} \cdot S_{\text{sem}} + w_{\text{int}} \cdot S_{\text{int}} + w_{\text{comp}} \cdot S_{\text{comp}} + w_{\text{term}} \cdot S_{\text{term}} + w_{\text{flu}} \cdot S_{\text{flu}}$$

Default Production Weights:
- **Semantic Accuracy ($w_{\text{sem}} = 0.35$)**: Preservation of the core proposition and communicative intent.
- **Data Integrity ($w_{\text{int}} = 0.25$)**: Verbatim accuracy of numbers, currencies, dates, URLs, and protected spans.
- **Completeness ($w_{\text{comp}} = 0.15$)**: Prevention of severe truncation or hallucinated expansion.
- **Terminology ($w_{\text{term}} = 0.15$)**: Adherence to customer/organization glossaries.
- **Fluency & Formatting ($w_{\text{flu}} = 0.10$)**: Target language grammar, natural phrasing, and punctuation balance.

## 2. Hard Safety Gate Constraint
Crucially:
$$\text{If } \text{has\_critical\_error} = \text{True} \implies S = \min(0.35, S_{\text{raw}})$$

A translation that says:
- Source: "Please do not restart the production server."
- Candidate: "कृपया अब उत्पादन सर्वर को पुनरारंभ करें।" (Fluent, but reversed meaning!)
will have $S_{\text{flu}} = 1.0$, but because $\text{has\_critical\_error} = \text{True}$, the overall score $S \le 0.35$ and the decision will immediately resolve to `RETRY_WITH_ALTERNATE_PROVIDER` or `REJECT`.

## 3. MQM-Aligned Error Taxonomy
Agent 05 categorizes every issue into four standard Multidimensional Quality Metrics (MQM) severity levels:

| Severity | Definition | Penalty | Typical Causes |
|---|---|---|---|
| **CRITICAL** | Alters factual meaning, reverses instructions, corrupts financial data, or leaks security tokens. | Gated ($S \le 0.35$) | Number mismatch, currency flip, negation reversal, wrong target script, leaked placeholder token. |
| **MAJOR** | Noticeable distortion of meaning or terminology violation that impedes comprehension. | -0.25 to -0.30 | Mandatory glossary term missing, severe phrase omission. |
| **MINOR** | Small grammatical, punctuation, or style discrepancy that does not impede comprehension. | -0.04 to -0.10 | Non-critical punctuation variance, minor casing differences. |
| **INFO** | Informational observation or telemetry signal. | 0.00 | Fallback provider invoked, partial chunk evaluated. |

