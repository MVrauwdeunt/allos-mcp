# Unreleased schema and container compatibility

The old reader required a direct `profile_id` even for tables on its allowlist. The decisions below compare the pre-PR reader with the upstream Allos migrations at `dc317160c5863258f50029851c3bfe770a8ea7b6`. Schemas that differ from this snapshot may expose a different subset of reviewed fields.

| Table | Decision and reason |
| --- | --- |
| `allergy_reactions` | Excluded. Ownership is indirect via `allergy_id` to `allergies`; reaction text is not reviewed for exposure. See migration `122`. |
| `exercise_sets` | Excluded. Ownership is indirect via `activity_id` to `activities`. See migration `006`. |
| `fitness_assessment_entries` | Excluded. Ownership is indirect via `assessment_id` to `fitness_assessments`; raw inputs are not reviewed for exposure. See migration `055`. |
| `food_daily_totals` | Restored with direct profile scoping: `id`, `profile_id`, `date`, `group_key`, `servings`, `created_at`. Notes are excluded. See migrations `030` and `20260814-persisted-vocabulary`. |
| `intake_item_logs` | Excluded. Ownership is indirect via `dose_id` to `intake_item_doses` and then `intake_items`; the optional `item_id` shortcut is not authoritative. See migration `011`. |
| `medication_courses` | Excluded. Ownership is indirect via `item_id` to `intake_items`; narrative and prescriber data are not reviewed for exposure. See migrations `001` and `091`. |
| `protein_daily_totals` | Restored with direct profile scoping: `id`, `profile_id`, `date`, `grams`, `created_at`. See migrations `053` and `20260814-persisted-vocabulary`. |
| `routine_days` | Excluded. Ownership is indirect via `routine_id` to `routines`. See migration `039`. |
| `sessions` | Excluded. This is an authentication table, not a health table. `active_profile_id` is a UI selection, not ownership, and the table holds token hashes. See migrations `001` and `102`. |
| `substance_daily_totals` | Restored with direct profile scoping: `id`, `profile_id`, `date`, `substance`, `units`. Only exact built-in keys (`alcohol`, `nicotine`, `cannabis`) are readable; custom labels, notes and provenance are excluded. See migration `20260814-persisted-vocabulary`. |

The six indirectly owned tables were already unavailable on the reviewed upstream schema. Supporting them would require separately reviewed parent joins and profile-isolation tests, not just additional allowlist entries.

Startup requires a real `metric_samples` table with `profile_id`, `metric`, `date` and `value`. It may contain zero rows. For `body_metrics`, `date` remains preferred when present; `recorded_at` supports variants without `date`. Pagination uses the same sort order regardless of which columns are requested. Offset pagination is not a snapshot across calls; concurrent writes can still shift pages.

## Released image versus unreleased source

Compose defaults to `ghcr.io/mvrauwdeunt/allos-mcp:0.2.0`. The `linux/amd64` and `linux/arm64` image configs identify revision `9b75196e82a78beb846f861cca2024b111f0d381`, the commit tagged `v0.2.0` before PR #1. The image includes HTTPS and Bearer authentication but does **not** include the allowlist, query changes, or startup checks described on this branch. To test those changes, build from the PR checkout and select the local image in Compose. Do not retag the existing release image with unreleased code.
