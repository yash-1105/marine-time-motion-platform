# Legacy KPI Definition Inventory and Retirement Plan

**Inventory date:** 2026-09-23 (local production-compatible PostgreSQL schema).
**Scope:** `analytics.kpi` rows with `code IS NULL`, before release migration
`m1n2o3p4q5r6` is applied to production.

The legacy rows are intentionally not deleted. The migration adds retirement
metadata, marks every unnumbered definition inactive, and preserves each primary
key. `analytics.kpi_result` and `analytics.kpi_benchmark` retain their existing
foreign keys; no result, benchmark, audit, report, or source-lineage row is
rewritten or deleted. The inventory checked direct result/benchmark references
and JSON/text references in audit events, dashboard snapshots, report payloads,
and Copilot messages. All were absent in the local inventory (`0` each).

`Governing alias` is populated only where equivalence is explicit. Blank means
**unmapped deliberately**: names such as `KPI_17` have no defensible semantic
mapping merely because they resemble a numbered identifier.

| Legacy database ID | Name | Formula/key | Results | Scorecard/report/audit/Copilot refs | Governing alias | Active use after migration |
|---|---|---|---|---|---|---|
| 4f1b6095-b037-4616-a8cf-4ed6599560fe | Anchorage Wait | null | no | no | KPI-03 | no |
| 841d283a-3780-4509-a9ca-16d6fe0591b0 | Berth Stay | null | no | KPI-15 | no |
| 77a363f3-ad69-4fd8-8c75-ec3453d548a3 | Turnaround | null | no | KPI-41 | no |
| 93e63eb4-4c68-4a9d-bf85-7b8f0bba727d | KPI_1 | null | no | no | — | no |
| 7b4a85c4-7839-4f21-b549-b08e04668ace | KPI_2 | null | no | no | — | no |
| 7de50e0e-0925-45ab-8a3a-224d70ec8397 | KPI_3 | null | no | no | — | no |
| d59802d4-18f6-4413-a155-0cb2add8e143 | KPI_4 | null | no | no | — | no |
| e47c1bc1-0c48-4914-aacc-08456c853f5d | KPI_5 | null | no | no | — | no |
| 98e4329f-c73d-4224-bfa2-47f004101aca | KPI_6 | null | no | no | — | no |
| f61bff1c-f5f5-4d50-9134-4dfc0cd70b8c | KPI_7 | null | no | no | — | no |
| 13be3c57-3eb4-4681-848d-73631ec516a0 | KPI_8 | null | no | no | — | no |
| 4bda1044-7974-4a5a-923c-2389ecfee668 | KPI_9 | null | no | no | — | no |
| efb030a3-12f8-4aaa-a991-262b10b718a0 | KPI_10 | null | no | no | — | no |
| 36b30f85-f3f9-412d-8bd3-dd55851b4992 | KPI_11 | null | no | no | — | no |
| 53b2d852-7b2b-46d9-a18f-13c111fa6b70 | KPI_12 | null | no | no | — | no |
| ecf36f31-84f0-4172-9a73-892885b24e43 | KPI_13 | null | no | no | — | no |
| d4d9afc8-a9f8-474e-9e8c-254dd739da81 | KPI_14 | null | no | no | — | no |
| 06805d1a-f294-4a2d-b305-865d8e2b9007 | KPI_15 | null | no | no | — | no |
| 0dc7db45-583b-4059-a8d7-fdb0d88912d0 | KPI_16 | null | no | no | — | no |
| 9bab3c1b-155b-4612-8eca-add0308e5183 | KPI_17 | null | no | no | — | no |
| 1e27c82a-faaf-411b-aa96-62c60880baa0 | KPI_18 | null | no | no | — | no |
| f7f92647-1764-41cf-aef6-0bddba5a1c90 | KPI_19 | null | no | no | — | no |
| 912d510d-95e1-49ee-88bb-7c0225bc9a21 | KPI_20 | null | no | no | — | no |
| 82e2e474-fa88-4097-9b2b-307be45564c3 | KPI_21 | null | no | no | — | no |
| 73308532-40a7-4ea9-a02e-0827b6f4d73e | KPI_22 | null | no | no | — | no |
| 2993bc40-7da8-4aa2-85d0-78ab09c7602f | KPI_23 | null | no | no | — | no |
| 76999ab8-e451-45a4-85b0-faaade56bf64 | KPI_24 | null | no | no | — | no |
| 2e956165-b540-4749-970f-7abcae065661 | KPI_25 | null | no | no | — | no |
| 7a8d028a-baca-45e1-a323-7facb6ea901e | KPI_26 | null | no | no | — | no |
| 4b1ea6cc-c00c-457d-8a1c-afc5c9225c40 | KPI_27 | null | no | no | — | no |
| 7d4ab41f-23be-4d02-a433-2a51f7c822f3 | KPI_28 | null | no | no | — | no |
| d6841ac2-1ccb-4ee3-99db-f4f44a1dbbce | KPI_29 | null | no | no | — | no |
| 6c647093-99e7-4a5e-a753-c1e94843ad40 | KPI_30 | null | no | no | — | no |
| 386a1d18-9706-4235-b682-f623b3f93973 | KPI_31 | null | no | no | — | no |
| 4c309c9d-a5bd-43b6-bca2-658fc6a40c0e | KPI_32 | null | no | no | — | no |
| 8155d0b8-6dfb-4e40-b753-273dba448e5a | KPI_33 | null | no | no | — | no |
| 0aa50251-c77d-4542-a4d6-786e0b582213 | KPI_34 | null | no | no | — | no |
| 767d8b72-91c5-42ca-9832-1b708abde2a5 | KPI_35 | null | no | no | — | no |
| 0a20b9dc-44ad-47f9-8815-d7472af666ab | KPI_36 | null | no | no | — | no |
| 5061052d-89ba-41a1-9bb7-aa3fe47d1eee | KPI_37 | null | no | no | — | no |
| 35eb3473-547f-495a-b266-70ea47c4bf1c | KPI_38 | null | no | no | — | no |
| 52f3e3a3-7b2b-48ae-8222-29519bd3b4e5 | KPI_39 | null | no | no | — | no |
| a473503a-25d0-436c-8ba9-29b231f3f30e | KPI_40 | null | no | no | — | no |
| 9b9510f6-cbbf-4594-bb70-69d91c7f0961 | KPI_41 | null | no | no | — | no |
| 6c480ea7-b0ae-4aa7-ac5c-71a351988dce | KPI_42 | null | no | no | — | no |
| fceabf22-1272-4971-9c2b-32e67c6986a9 | KPI_43 | null | no | no | — | no |
| a40ac2b6-13c7-4d8e-8e9a-26bea28facb8 | KPI_44 | null | no | no | — | no |
| 51c39b48-4cee-41b8-99e9-a2e8e44ddb4e | KPI_45 | null | no | no | — | no |
| 1660a70f-65d1-42a4-a8ba-98a8ff530e37 | KPI_46 | null | no | no | — | no |
| 18686440-7810-46d6-b728-4f5b2e52843e | KPI_47 | null | no | no | — | no |
| 6b6d9b75-9daa-4ec6-a9c2-fce8b146a529 | KPI_48 | null | no | no | — | no |
| 8030f1e1-8896-4d0d-93f6-06c8956672d5 | KPI_49 | null | no | no | — | no |
| 6bdbd072-a31b-43d7-af2d-d4009a7d6086 | KPI_50 | null | no | no | — | no |
| 29b42464-e4e8-4807-8c69-107038677f06 | KPI_51_Berth_Occupancy | null | no | no | — | no |
| a22a2855-c349-469e-bb59-e9cbdc8b965d | KPI_52 | null | no | no | — | no |
| e17b8123-6dd3-4148-8156-4ecb7a6b56ff | KPI_53_Tug_Response | null | no | no | — | no |
| 66278ceb-693b-4674-9197-75db6b0f847c | KPI_54 | null | no | no | — | no |
| a3f0e2af-8bf9-4949-8279-2d00f9a1513b | KPI_55 | null | no | no | — | no |

## Lineage-preserving retirement strategy

1. Migration `m1n2o3p4q5r6` adds `is_active`, `retired_at`,
   `retirement_reason`, and optional self-FK `governed_kpi_id` to
   `analytics.kpi`. It creates an `(is_active, kpi_number)` index for active
   catalogue reads.
2. Every `code IS NULL` legacy row becomes inactive with a timestamp/reason;
   primary IDs and every historical foreign-key relationship remain unchanged.
3. Only three explicitly named legacy metrics get a `governed_kpi_id` alias.
   The remaining 55 generic rows are preserved but deliberately not matched.
4. Registry APIs, scorecards, and `KPIEngine` query only `is_active = true`
   governed definitions. New results can therefore be written only to the 55
   numbered definitions.
5. Downgrade removes the retirement metadata/index only. It never deletes a KPI
   definition, result, benchmark, or audit event. A production rollback must be
   performed only after application rollback to a version that does not require
   these metadata columns.
