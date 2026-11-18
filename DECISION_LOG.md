# Project Decision Log – PS-062

Project: Diagnostic Lab Test Ordering and Report TAT Engine  
Team ID: T083

1. Python 3.10+ – Chosen for readable code and built-in date, time, and data-processing support.
2. Standard library only – Selected to avoid external dependencies and simplify project execution.
3. Decimal for currency – Used to prevent floating-point errors in billing and refunds.
4. Modular architecture – Adopted to separate parsing, business rules, routing, billing, and reporting.
5. Dataclasses and enums – Used to represent structured records and controlled status values.
6. CSV data format – Selected because input and output files are easy to read and validate.
7. Sequential command processing – Chosen to ensure deterministic execution of laboratory events.
8. Maximum fasting requirement – Applied to ensure all tests in an order satisfy the strictest fasting rule.
9. Tube-sharing limit – Set at four compatible tests per tube to reduce collection while respecting capacity.
10.Lowest capable lab routing – Selected to use laboratory tiers efficiently, with overflow handling when capacity is exhausted.
11. TAT calculation – Uses priority multipliers, a two-hour minimum, reference-lab transit time, and upward hour rounding.
12. Centralized billing – Used to handle panel pricing, duplicate tests, surcharges, fees, credits, and refunds consistently.
13. Event-based lifecycle management – Chosen to control sample rejection, recollection, cancellation, verification, and report release.
14. Python unittest framework – Selected for automated testing without installing additional packages.
15. Stretch goals – Added delta-checking and batch analyser scheduling to demonstrate additional laboratory workflows.