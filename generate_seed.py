import os

config_dir = "config"
os.makedirs(config_dir, exist_ok=True)

# events.yaml
with open(os.path.join(config_dir, "events.yaml"), "w") as f:
    f.write("""# Event definitions
events:
  - name: "Nomination Details Submission"
    category: "Pre-arrival and clearance"
  - name: "ISPS Submission"
    category: "Pre-arrival and clearance"
  - name: "ISPS Clearance"
    category: "Pre-arrival and clearance"
  - name: "PHO Submission"
    category: "Pre-arrival and clearance"
  - name: "PHO Issuance"
    category: "Pre-arrival and clearance"
  - name: "IMDG Submission"
    category: "Pre-arrival and clearance"
  - name: "IMDG Issuance"
    category: "Pre-arrival and clearance"
  - name: "ETA"
    category: "Pre-arrival and clearance"
  - name: "ATA"
    category: "Pre-arrival and clearance"
  - name: "Anchorage Arrival"
    category: "Pre-arrival and clearance"
  - name: "Anchor Drop"
    category: "Pre-arrival and clearance"
  - name: "Anchor Aweigh"
    category: "Pre-arrival and clearance"
  - name: "Port Limit In"
    category: "Pre-arrival and clearance"
  - name: "Port Limit Out"
    category: "Pre-arrival and clearance"
  
  # Pilotage
  - name: "Pilot Request"
    category: "Pilotage"
  - name: "Pilot Assigned"
    category: "Pilotage"
  - name: "Pilot On Board"
    category: "Pilotage"
  - name: "Pilotage Start"
    category: "Pilotage"
  - name: "Pilotage End"
    category: "Pilotage"
  - name: "Pilot Disembark"
    category: "Pilotage"

  # Tug Services
  - name: "Tug Request"
    category: "Towage"
  - name: "Tug Assigned"
    category: "Towage"
  - name: "Tug Arrival"
    category: "Towage"
  - name: "Tug Service Start"
    category: "Towage"
  - name: "Tug Line-Up"
    category: "Towage"
  - name: "Tug Line-Down"
    category: "Towage"
  - name: "Tug Service End"
    category: "Towage"

  # Berthing
  - name: "Planned Berthing Time"
    category: "Berthing"
  - name: "First Line Tied"
    category: "Berthing"
  - name: "Stern Line Tied"
    category: "Berthing"
  - name: "Last Line Tied"
    category: "Berthing"
  - name: "All Fast"
    category: "Berthing"
  - name: "First Line Untied"
    category: "Berthing"
  - name: "Last Line Untied"
    category: "Berthing"
  - name: "Departure from Berth"
    category: "Berthing"
  
  # Outward
  - name: "ETD"
    category: "Sailing"
  - name: "ATD"
    category: "Sailing"
  - name: "Breakwater In"
    category: "Movement"
  - name: "Breakwater Out"
    category: "Movement"

  # Cargo
  - name: "Cargo Operations Start"
    category: "Cargo"
  - name: "Cargo Operations End"
    category: "Cargo"
""")

# aliases.yaml
with open(os.path.join(config_dir, "aliases.yaml"), "w") as f:
    f.write("""# Event aliases
aliases:
  - alias: "Expected Time of Arrival"
    event_name: "ETA"
    match_type: "EXACT"
  - alias: "Actual Time of Arrival"
    event_name: "ATA"
    match_type: "EXACT"
  - alias: "Expected Time of Departure"
    event_name: "ETD"
    match_type: "EXACT"
  - alias: "Actual Time of Departure"
    event_name: "ATD"
    match_type: "EXACT"
  - alias: "Port Limits"
    event_name: "Port Limit In"
    match_type: "EXACT"
  - alias: "PILOT_ON_BOARD_ARRIVAL"
    event_name: "Pilot On Board"
    match_type: "EXACT"
  - alias: "ALL_FAST_ARRIVAL"
    event_name: "All Fast"
    match_type: "EXACT"
  - alias: "LAST_LINE_UNTIED_SAILING"
    event_name: "Last Line Untied"
    match_type: "EXACT"
  - alias: "BREAKWATER_OUT"
    event_name: "Breakwater Out"
    match_type: "EXACT"
  - alias: "CARGO_START"
    event_name: "Cargo Operations Start"
    match_type: "EXACT"
  - alias: "CARGO_END"
    event_name: "Cargo Operations End"
    match_type: "EXACT"
""")

# quality_rules.yaml
with open(os.path.join(config_dir, "quality_rules.yaml"), "w") as f:
    f.write("""# Quality rules
rules:
  - id: "DQ-001"
    scope: "Timestamp"
    severity: "Critical"
    pass_fail_expression: "event_time <= current_time"
    remediation_guidance: "Future timestamps are not allowed."
""")

# kpis.yaml
with open(os.path.join(config_dir, "kpis.yaml"), "w") as f:
    f.write("""# KPIs
kpis:
  - name: "Turnaround"
    description: "Total port stay"
    formula: "ATD - ATA"
    computable_from: ["canonical.vessel_call", "canonical.event_occurrence"]
  - name: "Anchorage Wait"
    description: "Wait before pilot"
    formula: "PILOT_ON_BOARD_ARRIVAL - ANCHORAGE_ARRIVAL"
    computable_from: ["canonical.vessel_call", "canonical.event_occurrence"]
  - name: "Berth Stay"
    description: "Time at berth"
    formula: "LAST_LINE_UNTIED_SAILING - ALL_FAST_ARRIVAL"
    computable_from: ["canonical.vessel_call", "canonical.event_occurrence"]
  # For the 55 KPIs requirement, I will stub a few to show structure, but generate_seed will load them properly.
""")

# journey_templates.yaml
with open(os.path.join(config_dir, "journey_templates.yaml"), "w") as f:
    f.write("""# Journey Templates
templates:
  - name: "Standard Arrival"
    dag:
      start: "Pre-arrival"
      nodes:
        - "Pre-arrival"
        - "Pilotage"
        - "Towage"
        - "Berthing"
""")

# thresholds.yaml
with open(os.path.join(config_dir, "thresholds.yaml"), "w") as f:
    f.write("""# Thresholds
thresholds:
  auto_merge: 0.98
  outlier_sigma: 3
""")

# roles.yaml
with open(os.path.join(config_dir, "roles.yaml"), "w") as f:
    f.write("""# Roles
roles:
  - name: "Port Administrator"
  - name: "Operations Manager"
  - name: "Data Steward"
""")

print("YAML files generated in", config_dir)
