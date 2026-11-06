# PS-062 – Diagnostic Lab Test Ordering and Report TAT Engine — Sample Data Pack

Prepared by 10 SECONDS for Team T083.

## Files

| File | What it holds | Row count |
|---|---|---|
| `tests.csv` | 150 tests with sample/tube type, fasting hours, standard TAT, tier, price and critical range | 150 data rows |
| `panels.csv` | 20 panels with bundled price | 20 data rows |
| `panel_tests.csv` | Panel membership | 99 data rows |
| `labs.csv` | 4 labs (2 x L1, L2, REFERENCE) with hours and coordinates | 4 data rows |
| `lab_capacity.csv` | Daily capacity per lab per sample type | 16 data rows |
| `courier_routes.csv` | Courier cut-offs, departures and transit between labs | 5 data rows |
| `phlebotomists.csv` | 6 phlebotomists for home collection | 6 data rows |
| `orders.csv` | 120 orders over 10 days | 120 data rows |
| `order_items.csv` | Tests and panels ordered | 294 data rows |
| `commands.txt` | Sample lifecycle events, rejections, waivers, doctor verifications, cancellations and prints | 2602 command lines (excluding comments) |

Row numbers quoted below are 1-based data-row numbers (the header is row 0). Line numbers for `commands.txt` are physical line numbers including comment lines.

## Column reference

Conventions: dates `YYYY-MM-DD`; timestamps `YYYY-MM-DD HH:MM:SS` (24h, IST, no timezone suffix); money in Rs as plain decimals with 2 places (no commas, no symbol); percentages as plain numbers (12.5 means 12.5%); booleans `true`/`false`; IDs uppercase with a fixed prefix. An empty cell means "not applicable / not supplied" and only occurs in columns whose notes say so.

### `tests.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| test_code | string | TST-nnn | — | — |
| test_name | string | — | — | — |
| sample_type | enum | — | BLOOD, URINE, SWAB, TISSUE | — |
| tube_type | enum | — | SST, EDTA, CITRATE, FLUORIDE, URINE_CUP, SWAB_TUBE, FORMALIN_JAR | same sample + tube type share a tube, max 4 tests per tube |
| fasting_hours | int | hours | — | 0 = none |
| std_tat_hours | int | hours | — | ROUTINE TAT |
| lab_tier | enum | — | L1, L2, REFERENCE | lowest tier able to run the test; a lab runs tests of its tier and below |
| price | decimal | Rs | — | — |
| critical_low | decimal | — | — | empty = no lower critical limit |
| critical_high | decimal | — | — | empty = none |
| unit | string | — | — | — |

### `panels.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| panel_id | string | PNL-nn | — | — |
| panel_name | string | — | — | — |
| price | decimal | Rs | — | bundled price |

### `panel_tests.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| panel_id | string | — | panels.csv | — |
| test_code | string | — | tests.csv | — |

### `labs.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| lab_id | string | LAB-nn | — | — |
| lab_name | string | — | — | — |
| tier | enum | — | L1, L2, REFERENCE | — |
| open_time | string | HH:MM | — | — |
| close_time | string | HH:MM | — | processing only between open and close |
| stat_24x7 | bool | — | — | STAT accepted outside hours |
| latitude | decimal | deg, 6 dp | — | — |
| longitude | decimal | deg, 6 dp | — | — |

### `lab_capacity.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| lab_id | string | — | labs.csv | — |
| sample_type | enum | — | BLOOD, URINE, SWAB, TISSUE | — |
| daily_capacity | int | tests/day | — | tests of that sample type the lab can take per calendar day; 0 = does not process |

### `courier_routes.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| from_lab_id | string | — | labs.csv | — |
| to_lab_id | string | — | labs.csv | — |
| cutoff_time | string | HH:MM | — | samples at the source lab at or before the cut-off leave today |
| departure_time | string | HH:MM | — | — |
| transit_minutes | int | min | — | physical transit (the brief's +24 h REFERENCE allowance is separate) |

### `phlebotomists.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| phleb_id | string | PHB-nn | — | — |
| phleb_name | string | — | — | — |
| base_lab_id | string | — | labs.csv | — |
| shift_start | string | HH:MM | — | — |
| shift_end | string | HH:MM | — | — |
| max_visits_per_day | int | — | — | — |

### `orders.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| order_id | string | ORD-nnnn | — | — |
| patient_name | string | — | — | — |
| age | int | years | — | — |
| gender | enum | — | M, F | — |
| order_ts | timestamp | — | — | — |
| priority | enum | — | ROUTINE, URGENT, STAT | — |
| collection_lab_id | string | — | labs.csv | local lab |
| home_collection | bool | — | — | — |
| slot_start | timestamp | — | — | 30-minute slot |
| address_lat | decimal | deg, 6 dp | — | home collection only |
| address_lon | decimal | deg, 6 dp | — | distance = haversine, R = 6371.0 km, compared after rounding to 2 dp |
| last_meal_ts | timestamp | — | — | empty when no fasting test is ordered |

### `order_items.csv`

| Column | Type | Units / format | Allowed values | Notes |
|---|---|---|---|---|
| order_id | string | — | orders.csv | — |
| item_type | enum | — | TEST, PANEL | — |
| item_code | string | — | tests.csv / panels.csv | — |

## Command file format

`commands.txt` holds one command per line in the form `COMMAND_NAME|arg1|arg2|...`. Commands must be processed strictly in file order. Lines starting with `#` are comments and blank lines are ignored. An empty argument (two adjacent `|`) means "not supplied". Every command used in this pack:

| Command | Arguments (in order) | Meaning |
|---|---|---|
| `COLLECTED` | `order_id|ts` | all tubes of the order collected (a repeat line = recollection) |
| `RECEIVED` | `order_id|test_code|ts` | physical arrival of the test's sample at the processing lab |
| `PROCESSING` | `order_id|test_code|ts` | processing started |
| `RESULTED` | `order_id|test_code|ts|value` | value empty for non-numeric results |
| `VERIFIED` | `order_id|test_code|ts|verifier_id` | pathologist verification |
| `DOCTOR_VERIFY` | `order_id|test_code|ts|doctor_id` | doctor verification required for a critical value |
| `REPORTED` | `order_id|test_code|ts` | report released for the test |
| `SAMPLE_REJECTED` | `order_id|test_code|ts|reason` | HAEMOLYSED, CLOTTED or INSUFFICIENT |
| `FASTING_WAIVER` | `order_id|ts` | patient waives the fasting breach |
| `CANCEL` | `order_id|item_code|ts` | item_code = test or panel code, or ALL |
| `PRINT_CAPACITY` | `date` | daily lab capacity report |
| `PRINT_TAT_BREACHES` | `from_date|to_date` | TAT breach report |
| `PRINT_ORDER` | `order_id` | order status with per-test times |

## Planted scenarios

Every edge case in the brief, mapped to the exact record where it occurs, followed by extra traps.

- **EC-01 Collection slot exactly N hours after the last meal**
  - ORD-0007: Lipid Profile needs 12 h fasting; last meal 2026-10-05 20:30, slot 2026-10-06 08:30 = exactly 12 h — valid, not NEEDS_RESCHEDULE — `orders.csv row 7`
- **EC-02 Fifth test needing the same tube (second tube required)**
  - ORD-0009: five SST/serum tests (max 4 per tube) + one EDTA test → 3 tubes (2 SST + 1 EDTA) → Rs 50 for the tube beyond the second — `order_items.csv rows 17, 18, 19, 20, 21, 22`
- **EC-03 Sample collected exactly at the courier cut-off time**
  - ORD-0028: walk-in at LAB-01, COLLECTED 2026-10-07 16:00:00 = exactly the LAB-01 → LAB-03 cut-off (16:00); Vitamin B12 (L2) leaves on the same day's 16:30 courier — `orders.csv row 28; commands.txt line 518`
- **EC-04 STAT with 0.25x of a 4-hour TAT giving 1 hour, raised to the 2-hour minimum**
  - ORD-0043: STAT Troponin I (standard TAT 4 h) collected 02:14 at L1 LAB-01 (24x7 for STAT) — 0.25 x 4 = 1 h is raised to the 2 h minimum; promised time 04:14 rounds up to 05:00 — `orders.csv row 43`
- **EC-05 Sample received one minute before the lab closes**
  - ORD-0060: home-collected sample reaches LAB-02 at 2026-10-09 20:59 — one minute before the 21:00 close, so it is RECEIVED immediately (not at the next opening) — `orders.csv row 60`
- **EC-06 Panel plus one member test plus a second overlapping panel in one order**
  - ORD-0057: Kidney Function Test panel + Serum Potassium (a KFT member → removed, not charged) + Electrolytes panel (overlaps KFT on Na/K/Cl → both panels charged, shared tests run once) — `order_items.csv rows 141, 142, 143`
- **EC-07 Home collection at exactly 10 km and order value exactly Rs 2,000**
  - ORD-0073: home address exactly 10.00 km (haversine) from LAB-01 → Rs 200 band; ROUTINE order value exactly Rs 2,000.00 (Vitamin D 1,150 + HbA1c 450 + Total T3 250 + Platelet Count 150) → fee waived — `orders.csv row 73`
- **EC-08 Report delayed by exactly 2 hours**
  - ORD-0086: Serum Calcium (6 h, L1) collected 09:20 → promised 15:20 rounds up to 16:00; REPORTED at 18:00 = exactly 2 h late — not 'more than 2 hours', no credit — `commands.txt line 2050`
- **Extra traps (not in the brief, but realistic):**
  - ORD-0024: COLLECTED 16:01 — one minute after the cut-off: departs next day (2026-10-08 16:30) and the TAT clock keeps running — `orders.csv row 24`
  - ORD-0045: Fasting Blood Sugar needs 10 h but last meal 23:30 → slot 07:00 is 7.5 h; patient waives → results flagged NON_FASTING and no delayed-report credit — `commands.txt line 1068`
  - ORD-0048: 7 h after the last meal for a 10 h fasting test, no waiver → NEEDS_RESCHEDULE (no lifecycle events follow) — `orders.csv row 48`
  - ORD-0018: Serum Potassium rejected (haemolysed), free recollection within 24 h (TAT clock restarts), rejected again → that test is cancelled with a full refund and the CBC is released as a partial report — `commands.txt line 323, line 748, line 763, line 770`
  - ORD-0113: Serum Potassium 6.8 is above the critical high 6.2 → VERIFIED only via DOCTOR_VERIFY at 12:40; REPORTED 13:41 = 61 minutes later → critical breach — `commands.txt line 2185 and line 2202`
  - ORD-0089: home collection 25.6 km from LAB-02 — beyond 25 km, not offered (reject the order) — `orders.csv row 89`
  - LAB-02 has URINE capacity 4/day; five Urine Routine orders collected there on 2026-10-13 — the fifth is couriered to LAB-03 (next tier) — `orders.csv rows 94, 103, 105, 109, 110`
  - ORD-0118: Thyroid panel cancelled after COLLECTED, before PROCESSING — 50% of the panel price is charged (panel cancellation is all-or-nothing) — `commands.txt line 2383`

## What is NOT in this pack

Expected outputs are not provided for this set. Validate your engine with your own test suite against the rules in your brief (BR-01 … BR-nn). A separate hidden input set with the same schema will be used at final evaluation; outputs are compared field-for-field, so follow the column formats above exactly in your own output.

## Output format expected at evaluation

Produce these CSV files (header row, same conventions as above, rows sorted as stated). Where the brief is silent on a format detail the choice below is binding for evaluation.

### `order_tests.csv`

One row per unique test per order.

Columns, in order: `order_id`, `test_code`, `routed_lab_id`, `routing_reason`, `collected_ts`, `received_ts`, `promised_ts`, `reported_ts`, `status`, `tat_breach_hours`, `flags`

### `status_history.csv`

One row per state change.

Columns, in order: `order_id`, `test_code`, `status`, `ts`

### `bills.csv`

One row per order.

Columns, in order: `order_id`, `tests_amount`, `panels_amount`, `duplicate_removed`, `priority_surcharge`, `tube_fee`, `home_collection_fee`, `cancellation_charge`, `delay_credit`, `refund`, `net_amount`

### `tat_breaches.csv`

One row per breached test.

Columns, in order: `order_id`, `test_code`, `promised_ts`, `reported_ts`, `delay_minutes`, `credit_pct`, `credit_amount`, `breach_type`

### `capacity_report.csv`

One row per lab per sample type per PRINT_CAPACITY.

Columns, in order: `date`, `lab_id`, `sample_type`, `capacity`, `used`, `overflow_routed`

Binding choices: test `status` is the latest of COLLECTED, RECEIVED, PROCESSING, RESULTED, VERIFIED, REPORTED, REJECTED_SAMPLE, NEEDS_RESCHEDULE, CANCELLED; `flags` is `;`-separated from NON_FASTING, CRITICAL, OVERRIDE_BEDS-style codes you define; `breach_type` is TAT or CRITICAL.
