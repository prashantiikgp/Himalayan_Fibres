# Data v3 build report

## Row counts: source → cleaned

| Category | Raw rows | Within-file collapsed | Unreachable dropped | Cross-file dropped | Final |
|---|---:|---:|---:|---:|---:|
| existing_client | 11 | 0 | 1 | 0 | 10 |
| lapsed_client | 35 | 2 | 6 | 1 | 26 |
| carpet_exporter_lead | 934 | 106 | 0 | 22 | 806 |
| yarn_store_lead | 1580 | 394 | 22 | 0 | 1164 |

## Reachability of surviving rows

| Category | Final | With email | With phone |
|---|---:|---:|---:|
| existing_client | 10 | 9 | 10 |
| lapsed_client | 26 | 23 | 25 |
| carpet_exporter_lead | 806 | 806 | 806 |
| yarn_store_lead | 1164 | 804 | 1142 |

## Cross-file collisions (lower-priority bucket lost the row)

| Dropped from | Already in | Count |
|---|---|---:|
| carpet_exporter_lead | existing_client | 6 |
| carpet_exporter_lead | lapsed_client | 16 |
| lapsed_client | existing_client | 1 |

## Country distribution per category


**existing_client**

| Country | Count |
|---|---:|
| India | 10 |

**lapsed_client**

| Country | Count |
|---|---:|
| India | 26 |

**carpet_exporter_lead**

| Country | Count |
|---|---:|
| India | 806 |

**yarn_store_lead**

| Country | Count |
|---|---:|
| USA | 1133 |
| Netherlands | 31 |

## Validation

All invariants hold. No email/phone appears in more than one category.
