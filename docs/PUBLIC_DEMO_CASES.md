# Public demo case catalog

RideResolve exposes two strictly separated data classes:

- `OFFICIAL_HACKATHON_SAMPLE`: three supplied samples (`DISP-001` through `DISP-003`), stored in `data/cases/official_cases.json`.
- `SYNTHETIC_DEMO`: nine fictional scenarios (`DEMO-*`), stored in `data/cases/synthetic_demo_cases.json`.

If a case identity or evidence identity conflicts, the official dataset is loaded last and wins. Synthetic cases have no production effect and execute no real refund, fee adjustment, or notification.

## Copy-ready demo prompts

| Reference | Common scenario | Expected deterministic outcome | Prompt |
|---|---|---|---|
| `DEMO-101` / `TRIP-2026-20101` | Verified detour disclosed to rider | `RD-103`, no action | `Please review demo case DEMO-101. The route was longer, but the driver warned me about a road closure.` |
| `DEMO-102` / `TRIP-2026-20102` | Unjustified longer route | `RD-105`, refund SGD 3.80 | `Please review trip TRIP-2026-20102. The driver took an unexplained longer route.` |
| `DEMO-103` / `TRIP-2026-20103` | Missing route GPS | `RD-101`, human review | `Please review demo case DEMO-103. Part of the GPS record is missing.` |
| `DEMO-201` / `TRIP-2026-20201` | Driver marked arrival too far away | `NS-103`, refund SGD 5.00 | `Please review trip TRIP-2026-20201. The driver marked arrival far from the pickup point.` |
| `DEMO-202` / `TRIP-2026-20202` | Driver waited too briefly | `NS-104`, refund SGD 5.00 | `Please review demo case DEMO-202. The driver cancelled before the minimum waiting time.` |
| `DEMO-203` / `TRIP-2026-20203` | Driver did not use both contact channels | `NS-105`, refund SGD 5.00 | `Please review trip TRIP-2026-20203. The driver did not call before cancelling.` |
| `DEMO-301` / `TRIP-2026-20301` | Notified surge increase | `FD-102`, no action | `Please review demo case DEMO-301. The surge increase was shown before pickup.` |
| `DEMO-302` / `TRIP-2026-20302` | Unnotified surge increase | `FD-103`, refund SGD 5.25 | `Please review trip TRIP-2026-20302. The final fare included an unannounced surge increase.` |
| `DEMO-303` / `TRIP-2026-20303` | Missing notification record | `FD-101`, human review | `Please review demo case DEMO-303. The fare notification record is unavailable.` |

## Regeneration and verification

```powershell
python scripts/generate_public_demo_cases.py
python -m pytest -q tests/test_public_demo_cases.py tests/test_intake_session.py
```

Do not edit the generated JSON manually. The generator recalculates every evidence checksum and the tests reproduce every expected decision from deterministic policy code.
