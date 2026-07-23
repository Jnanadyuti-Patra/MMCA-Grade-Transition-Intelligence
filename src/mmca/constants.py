from __future__ import annotations

POUNDS_PER_METRIC_TONNE = 2204.62262185

PRODUCT_COLUMNS = {
    "coil_id": ["Coil ID"],
    "internal_id": ["9 Digit Internal Coil ID"],
    "date": ["Date"],
    "start_time": ["Start Time"],
    "finish_time": ["Finish Time"],
    "grade": ["Grade"],
    "net_weight": ["Net"],
    "downgrade_code": ["Downgrade code"],
    "manual_selected": ["Check Box Manual selected"],
    "manual_remarks": ["Txt_Manual_Grading_Remarks"],
    "remarks": ["Remarks"],
    "contaminated": ["Contaminated"],
}

PRODUCT_PARAMETER_COLUMNS = {
    "Diameter": {
        "kind": "pair",
        "columns": ["Min.Diameter (mm)", "Max.Diameter (mm)"],
        "group": "Dimensions",
    },
    "Tensile strength": {
        "kind": "single",
        "columns": ["Tensile strength (N/mm2)"],
        "group": "Mechanical properties",
    },
    "Elongation": {
        "kind": "single",
        "columns": ["Elongation (%)"],
        "group": "Mechanical properties",
    },
    "Conductivity": {
        "kind": "single",
        "columns": ["Conductivity"],
        "group": "Electrical quality",
    },
    "Large surface defects": {
        "kind": "single",
        "columns": ["Large surface"],
        "group": "Surface quality",
    },
    "Medium surface defects": {
        "kind": "single",
        "columns": ["Medium Surface"],
        "group": "Surface quality",
    },
    "Small surface defects": {
        "kind": "single",
        "columns": ["Small Surface"],
        "group": "Surface quality",
    },
    "Large ferrous defects": {
        "kind": "single",
        "columns": ["Large Ferrous"],
        "group": "Surface quality",
    },
    "Medium ferrous defects": {
        "kind": "single",
        "columns": ["Medium Ferrous"],
        "group": "Surface quality",
    },
    "Small ferrous defects": {
        "kind": "single",
        "columns": ["Small Ferrous"],
        "group": "Surface quality",
    },
    "Oxygen": {
        "kind": "single",
        "columns": ["Oxygen (ppm)"],
        "group": "Oxygen and oxides",
    },
    "25 RTF twist": {
        "kind": "single",
        "columns": ["F/R 25 twist"],
        "group": "Mechanical properties",
    },
    "Oxide content": {
        "kind": "single",
        "columns": ["Total Oxide"],
        "group": "Oxygen and oxides",
    },
    "15 × 15 twist": {
        "kind": "single",
        "columns": ["15/15 Twist Test"],
        "group": "Mechanical properties",
    },
    "Aluminium": {"kind": "single", "columns": ["Aluminium (Al)"], "group": "Chemistry"},
    "Antimony": {"kind": "single", "columns": ["Antimony (Sb)"], "group": "Chemistry"},
    "Arsenic": {"kind": "single", "columns": ["Arsenic (As)"], "group": "Chemistry"},
    "Bismuth": {"kind": "single", "columns": ["Bismuth (Bi)"], "group": "Chemistry"},
    "Cadmium": {"kind": "single", "columns": ["Cadmium (Cd)"], "group": "Chemistry"},
    "Iron": {"kind": "single", "columns": ["Iron (Fe) (ppm)"], "group": "Chemistry"},
    "Lead": {"kind": "single", "columns": ["Lead (Pb)"], "group": "Chemistry"},
    "Nickel": {"kind": "single", "columns": ["Nickel (Ni)"], "group": "Chemistry"},
    "Phosphorus": {"kind": "single", "columns": ["Phosphorus (P)"], "group": "Chemistry"},
    "Selenium": {"kind": "single", "columns": ["Selenium (Se)"], "group": "Chemistry"},
    "Sulphur": {"kind": "single", "columns": ["Sulphur (S)"], "group": "Chemistry"},
    "Tellurium": {"kind": "single", "columns": ["Tellurium (Te)"], "group": "Chemistry"},
    "Tin": {"kind": "single", "columns": ["Tin (Sn)"], "group": "Chemistry"},
    "Zinc": {"kind": "single", "columns": ["Zinc (Zn)"], "group": "Chemistry"},
}

IMPORTANT_PROCESS_PARAMETERS = {
    "SV Temp": "Thermal control",
    "HF Temp": "Thermal control",
    "Tundish Temp": "Thermal control",
    "WHEEL_TEMP": "Thermal control",
    "BAR_ENTRY_TEMP": "Thermal control",
    "BAR_RM_ENTRY_TEMP": "Thermal control",
    "ROD_SPEED": "Casting and line speed",
    "WEIGHT_HF": "Casting and line speed",
    "SOLUBLE_OIL_TEMP": "Lubrication and NAPS",
    "SOLUBLE_OIL_CONC": "Lubrication and NAPS",
    "SOLUBLE_IPA_CONC": "Lubrication and NAPS",
    "NAPS_FLOW_ZONE1": "Lubrication and NAPS",
    "NAPS_CONC": "Lubrication and NAPS",
    "NAPS_IPA_CONC": "Lubrication and NAPS",
    "WAX_CONC": "Lubrication and NAPS",
    "DA_WHEEL_BOTTOM_FLOW": "Cooling-flow balance",
    "O2_WHEEL_BOTTOM_FLOW": "Cooling-flow balance",
    "DA_WHEEL_SIDE_FLOW": "Cooling-flow balance",
    "O2_WHEEL_SIDE_FLOW": "Cooling-flow balance",
    "DA_BAND_FLOW": "Cooling-flow balance",
    "O2_BAND_FLOW": "Cooling-flow balance",
    "NIP_NOZZLE_FLOW": "Cooling-flow balance",
    "BAND1_FLOW": "Cooling-flow balance",
    "BAND2_FLOW": "Cooling-flow balance",
    "BAND3_FLOW": "Cooling-flow balance",
    "WHEEL1_FLOW": "Cooling-flow balance",
    "WHEEL2_FLOW": "Cooling-flow balance",
    "WHEEL3_FLOW": "Cooling-flow balance",
    "WHEEL_MACHINE_SIDE_FLOW": "Cooling-flow balance",
    "WHEEL_OPERATOR_SIDE_FLOW": "Cooling-flow balance",
    "AFTER_COOLER1_FLOW": "Cooling-flow balance",
    "AFTER_COOLER2_FLOW": "Cooling-flow balance",
    "AFTER_COOLER3_FLOW": "Cooling-flow balance",
    "SRIPPER_SHOE_FLOW": "Cooling-flow balance",
}


PROCESS_PLAUSIBLE_RANGES = {
    "SV Temp": (0.0, 1500.0),
    "HF Temp": (0.0, 1500.0),
    "Tundish Temp": (900.0, 1300.0),
    "WHEEL_TEMP": (0.0, 400.0),
    "BAR_ENTRY_TEMP": (400.0, 1200.0),
    "BAR_RM_ENTRY_TEMP": (400.0, 1200.0),
    "ROD_SPEED": (0.0, 100.0),
    "WEIGHT_HF": (0.0, 500.0),
    "NAPS_CONC": (0.0, 2000.0),
    "NAPS_FLOW_ZONE1": (0.0, 500.0),
    "SOLUBLE_IPA_CONC": (0.0, 10.0),
}
for _parameter in IMPORTANT_PROCESS_PARAMETERS:
    if _parameter.endswith("_FLOW") or "FLOW" in _parameter:
        PROCESS_PLAUSIBLE_RANGES.setdefault(_parameter, (0.0, 1000.0))
    if "CONC" in _parameter:
        PROCESS_PLAUSIBLE_RANGES.setdefault(_parameter, (0.0, 100.0))

PROCESS_GROUP_RELEVANCE = {
    "Oxygen and oxides": {
        "Thermal control": 1.0,
        "Casting and line speed": 0.9,
        "Cooling-flow balance": 0.8,
        "Lubrication and NAPS": 0.5,
    },
    "Surface quality": {
        "Cooling-flow balance": 1.0,
        "Lubrication and NAPS": 0.95,
        "Casting and line speed": 0.75,
        "Thermal control": 0.7,
    },
    "Dimensions": {
        "Casting and line speed": 1.0,
        "Cooling-flow balance": 0.75,
        "Thermal control": 0.6,
    },
    "Mechanical properties": {
        "Thermal control": 0.9,
        "Cooling-flow balance": 0.85,
        "Casting and line speed": 0.8,
        "Lubrication and NAPS": 0.45,
    },
    "Electrical quality": {
        "Thermal control": 0.85,
        "Casting and line speed": 0.75,
        "Cooling-flow balance": 0.55,
        "Lubrication and NAPS": 0.4,
    },
    "Chemistry": {
        "Thermal control": 0.75,
        "Casting and line speed": 0.65,
        "Cooling-flow balance": 0.35,
        "Lubrication and NAPS": 0.25,
    },
}

ACTION_LIBRARY = {
    "Thermal control": {
        "title": "Stabilise tundish and bar-entry temperatures",
        "actions": [
            "Verify calibration and response time of tundish, SV, HF, wheel and bar-entry temperature sensors.",
            "Review setpoint-versus-actual trends around the highest-scoring transitions and define alarm bands for sustained drift.",
            "Inspect launder heat loss, burner control and thermocouple placement when thermal deviations repeatedly precede oxygen or oxide-related downgrades.",
        ],
        "verification": "Track the percentage of coils produced inside the approved tundish and bar-temperature window and the downgrade rate that follows thermal alarms.",
    },
    "Cooling-flow balance": {
        "title": "Balance wheel, band and after-cooler water flows",
        "actions": [
            "Inspect nozzles, strainers, pumps and control valves for blockage, fouling or unequal flow distribution.",
            "Create side-to-side imbalance alarms for machine-side and operator-side wheel flows.",
            "Standardise pre-shift checks for wheel, band, nip-nozzle and after-cooler flows before high-grade production campaigns.",
        ],
        "verification": "Monitor flow imbalance percentage and the frequency of surface, oxide and mechanical-property downgrades after corrective maintenance.",
    },
    "Casting and line speed": {
        "title": "Reduce abrupt casting and rod-speed changes",
        "actions": [
            "Review rod-speed ramps and synchronisation with casting conditions around transition events.",
            "Check encoder health and investigate sudden speed steps that occur before one-coil grade fluctuations.",
            "Define controlled ramp limits during grade-sensitive customer orders and startup recovery.",
        ],
        "verification": "Compare transition frequency before and after applying speed-ramp limits and encoder checks.",
    },
    "Lubrication and NAPS": {
        "title": "Tighten soluble-oil, IPA, NAPS and wax control",
        "actions": [
            "Increase checks of concentration and temperature during periods with repeated surface-quality transitions.",
            "Verify dosing, mixing and replenishment procedures and investigate sensor-versus-laboratory discrepancies.",
            "Link bath maintenance records to coil IDs so recurring surface defects can be traced to treatment condition.",
        ],
        "verification": "Track bath concentration compliance and surface-defect transition rates by maintenance cycle.",
    },
    "Chemistry / raw material": {
        "title": "Strengthen raw-material and chemistry traceability",
        "actions": [
            "Record cathode, in-house scrap and external scrap proportions with charge timestamps and batch identifiers.",
            "Review oxygen and impurity trends against charging changes and phosphorus-shot additions.",
            "Use the charging log as an additional input before assigning raw-material causation.",
        ],
        "verification": "Measure the share of chemistry-related downgrades that can be linked to a complete charge record.",
    },
    "Startup / shutdown": {
        "title": "Separate startup and stoppage coils from steady-state production",
        "actions": [
            "Use a documented startup acceptance sequence before assigning customer-grade production.",
            "Record the exact plant stop/start reason and stabilisation time against the affected coil IDs.",
            "Hold transition coils until tundish temperature, rod speed and cooling flows remain stable for the approved period.",
        ],
        "verification": "Track the percentage of startup and stoppage coils requiring downgrade or remelt.",
    },
    "Manual / contamination": {
        "title": "Strengthen manual-grade and contamination traceability",
        "actions": [
            "Require a structured reason code and approving person for every manual grade override.",
            "Record contamination source, affected length and disposition against the coil ID.",
            "Review recurring manual grades separately from statistically inferred process causes.",
        ],
        "verification": "Monitor the number of manual-grade and contaminated events without a complete reason code.",
    },
    "Data quality": {
        "title": "Repair unreliable or frozen measurement channels",
        "actions": [
            "Calibrate channels with impossible values, repeated constants or excessive missing data.",
            "Add validation limits at data capture so sensor faults cannot be interpreted as process deviations.",
            "Document planned shutdown and inactive-channel periods.",
        ],
        "verification": "Monitor missing-value rate, frozen-channel count and the percentage of transitions classified as insufficient evidence.",
    },
}
