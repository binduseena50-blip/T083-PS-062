# PS-062 · Diagnostic Lab Test Ordering and Report TAT Engine

**Team:** T083  
**Domain:** Healthcare – Diagnostics  
**Difficulty:** Medium-High  
**Language:** Python 3.10+ (Standard Library, Zero External Dependencies)

---

## 📌 Project Overview
PS-062 is an enterprise-grade, command-file-driven back-end engine engineered for diagnostic laboratory chains. It accepts laboratory test orders, validates biological fasting requirements, computes turnaround-time (TAT) commitments, routes specimens across multi-tier laboratories with daily capacity overflow management, executes specimen life-cycle state transitions, and settles billing with panel deduplication, home-collection fees, and delayed-report credits.

---

## 🏗️ Architecture & Business Rules Summary

The engine is built on 14 formal business rules:
* **BR-01 (Fasting Window):** Validates collection slot against patient's last meal; enforces `NEEDS_RESCHEDULE` or `FASTING_WAIVER` (flags `NON_FASTING`).
* **BR-02 (Tube Sharing):** Groups tests by `(sample_type, tube_type)` (max 4 tests/tube); extra tube fee of Rs 50/tube beyond 2.
* **BR-03 (Multi-Tier Routing & Overflow):** Routes to lowest capable lab tier; handles courier cut-offs and daily capacity overflow (`CAPACITY_OVERFLOW`).
* **BR-04 (Promised TAT):** Priority multipliers (ROUTINE $1.0\times$, URGENT $0.5\times$, STAT $0.25\times$, min 2h), $+24$h REFERENCE allowance, rounds up to next whole hour.
* **BR-05 (Operating Hours):** Processing strictly within lab hours; continuous 24x7 TAT clock; 24x7 STAT intake at L1.
* **BR-06 (Rejections & Recollections):** Free recollection within 24h; double rejection cancels test with 100% refund and releases partial report.
* **BR-07 (Critical Values):** Results outside critical range require `DOCTOR_VERIFY`; must be reported within 1h or triggers `CRITICAL` breach.
* **BR-08 (Pricing & Panels):** Deduplicates individual tests ordered alongside panels; overlapping panels charged both but shared tests run once; priority surcharges.
* **BR-09 (Home Collection):** Haversine distance banding ($\le 10$ km: Rs 200, $10\text{--}25$ km: Rs 400, $> 25$ km: rejected); fee waived if order value $\ge \text{Rs } 2,000$.
* **BR-10 (Delayed-Report Credits):** $> 2$h delay: 10% credit; $> 24$h delay: 50% credit (exempt if recollection or waived fasting).
* **BR-11 (Cancellations):** Free before collection; 50% fee after collection and before processing; no refund after processing.
* **BR-12 (Report Release):** All tests verified before release, except STAT tests which release individually immediately upon verification.
* **BR-13 (Delta-Check Engine - Stretch Goal):** Flags results differing by $> 30\%$ from previous result for re-run.
* **BR-14 (Batch Analyser Scheduling - Stretch Goal):** Batches analyzer runs when 10 samples accumulate or 2 hours elapse.

Full specifications, Mermaid state machine diagrams, and viva defense answers are documented in [DESIGN.md](DESIGN.md).

---

## 🚀 Quick Start & Execution

### 1. Run the Engine
```bash
python main.py
```
This loads all master data, executes `commands.txt`, prints live capacity and breach reports, and exports all 5 evaluation CSV files into the `output/` directory.

### 2. Run with Custom / Evaluation Data
```bash
python main.py --data-dir "path/to/data" --commands "path/to/commands.txt" --output-dir "output"
```

### 3. Run Automated Tests (24 Unit & Integration Tests)
```bash
python -m unittest discover -s tests
```

---

## 📊 Canonical Evaluation Outputs (`output/`)

The engine generates the 5 mandatory CSV files required for evaluation:
1. `order_tests.csv`: Unique tests per order, routed lab, routing reason, promised/reported timestamps, status, breach hours, and flags.
2. `status_history.csv`: Complete state change audit log (`COLLECTED`, `RECEIVED`, `PROCESSING`, `RESULTED`, `VERIFIED`, `REPORTED`, `CANCELLED`).
3. `bills.csv`: Full financial reconciliation (tests amount, panels amount, duplicate removed, surcharge, tube fee, home collection fee, cancellation charges, delay credits, refunds, net amount).
4. `tat_breaches.csv`: All breached tests with delay in minutes, credit %, credit amount, and breach type (`TAT` or `CRITICAL`).
5. `capacity_report.csv`: Daily lab capacity, used capacity, and overflow-routed counts.

---

## 📂 Project Structure

```
.
├── engine/                   # Core modular engine package
│   ├── models.py             # Domain dataclasses and enumerations
│   ├── parser.py             # CSV and command file loaders
│   ├── rules.py              # BR-01 through BR-12 business rule implementations
│   ├── router.py             # Multi-tier routing & capacity overflow tracker
│   ├── billing.py            # Pricing, panel deduplication, tube and home fees
│   ├── lifecycle.py          # State machine, doctor verification & release manager
│   ├── reporter.py           # Evaluation CSV generators and console formatters
│   ├── core.py               # Central engine coordinator
│   └── stretch.py            # Stretch goals (Delta check & Batch scheduling)
├── main.py                   # Command-file driven CLI entry point
├── DESIGN.md                 # Design document, Business Rules Register & Viva Guide
├── tests/                    # 24 Unit and integration test suite
│   ├── test_fasting.py       # BR-01 & EC-01 tests
│   ├── test_tube_sharing.py  # BR-02 & EC-02 tests
│   ├── test_tat.py           # BR-04, BR-10, EC-04 & EC-08 tests
│   ├── test_routing.py       # BR-03, BR-05, EC-03 & EC-05 tests
│   ├── test_pricing.py       # BR-08, BR-09, EC-06 & EC-07 tests
│   ├── test_lifecycle.py     # BR-06, BR-07, BR-11 & BR-12 tests
│   ├── test_stretch.py       # BR-13 & BR-14 stretch goal tests
│   └── test_integration.py   # Full end-to-end integration test
├── output/                   # Canonical CSV reports for evaluation
└── sample_data/              # Master data CSVs and commands.txt
```
