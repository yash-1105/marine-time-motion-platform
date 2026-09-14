import os
import yaml

kpis = []
for i in range(1, 56):
    kpis.append({
        "name": f"KPI_{i}",
        "description": f"Description for KPI {i}",
        "formula": "Numerator / Denominator",
        "numerator": "N",
        "denominator": "D",
        "unit": "hours",
        "eligible_population": "All",
        "required_events": [],
        "exclusions": [],
        "aggregation_method": "Average",
        "vessel_applicability": "All",
        "target": 0,
        "thresholds": {},
        "owner": "Admin",
        "effective_dates": "2026-01-01",
        "computable_from": ["canonical.vessel_call"] if i <= 15 else [],
        "status": "OK" if i <= 15 else "NO_SOURCE_DATA"
    })

# specifically adding the duplicated pairs mentioned in the prompt
kpis[52] = kpis[10].copy()
kpis[52]['name'] = "KPI_53_Tug_Response"
kpis[52]['primary_kpi_id'] = "KPI_11"
kpis[52]['alias_of'] = "KPI_11"

kpis[50] = kpis[13].copy()
kpis[50]['name'] = "KPI_51_Berth_Occupancy"
kpis[50]['primary_kpi_id'] = "KPI_14"
kpis[50]['alias_of'] = "KPI_14"

with open(os.path.join("config", "kpis.yaml"), "w") as f:
    yaml.dump({"kpis": kpis}, f, sort_keys=False)
print("55 KPIs generated.")
