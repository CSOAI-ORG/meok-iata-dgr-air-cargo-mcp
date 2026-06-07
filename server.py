#!/usr/bin/env python3
"""
MEOK IATA DGR Air Cargo Compliance MCP
========================================

By MEOK AI Labs · https://haulage.app · MIT
<!-- mcp-name: io.github.CSOAI-ORG/meok-iata-dgr-air-cargo-mcp -->

WHAT THIS DOES
--------------
Air freight of Dangerous Goods is governed by ICAO Annex 18 + the Technical
Instructions (Doc 9284), implemented by airlines through the IATA Dangerous
Goods Regulations (DGR 66th edition 2025).

This MCP extends MEOK from road (ADR) → air. Forwarders + car-transporters
moving batteries / recalled EVs by air freight face very different rules:
  - Lithium batteries are heavily restricted (PI 965-970)
  - State of charge MUST be ≤ 30% for Li-ion (Section IA/IB) under PI 965
  - Cargo Aircraft Only (CAO) restrictions apply to many items
  - Shipper's Declaration is mandatory (§8) for most DG
  - Per-operator + per-state variations (FedEx vs UPS vs Cathay all differ)
  - Acceptance checklist (§9) at carrier handover

A single mis-declared Li-ion shipment = up to $250,000 FAA fine + carrier
embargo + lost route. This MCP gives the callable compliance toolkit.

TOOLS (8)
---------
- classify_air_dangerous_good(material)            → 9 ICAO/IATA classes + UN
- check_lithium_battery_air_transport(spec)        → UN3480/3481/3090/3091 PI
- check_state_of_charge_air(soc_pct)               → Li-ion ≤30% air rule
- generate_iata_shippers_declaration(consignment)  → IATA DGR §8 paperwork
- check_passenger_vs_cargo_aircraft(material, ac)  → CAO restrictions
- validate_un_specification_packaging(marks)       → UN 4G/4D/3H1 codes
- check_country_variations(material, countries)    → state + operator vars
- prepare_iata_acceptance_check(consignment)       → §9 acceptance procedure

WHY YOU PAY
-----------
Single avoided mis-declaration = up to $250k FAA fine + embargo savings.
Forwarders + EV-recall carriers using air freight rely on this for
Shipper's Declaration generation + Section II compliance + CAO routing.

PRICING
-------
Free MIT self-host · £99/mo Starter · £299/mo Pro · £1,499/mo Fleet.

REGULATORY BASIS
----------------
ICAO Annex 18 — The Safe Transport of Dangerous Goods by Air
ICAO Doc 9284 — Technical Instructions (TI) 2025-2026 edition
IATA Dangerous Goods Regulations 66th edition (1 January 2025)
UN Model Regulations on the Transport of Dangerous Goods (23rd revised)
49 CFR Parts 171-180 — US DOT/PHMSA Hazardous Materials
CAA UK CAP 1349 — Aircraft DG operator approvals
EASA Part-CAT.GEN.MPA.200 — Carriage of dangerous goods
"""

from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone, date
from typing import Optional
from mcp.server.fastmcp import FastMCP


mcp = FastMCP("meok-iata-dgr-air-cargo")
_HMAC_SECRET = os.environ.get("MEOK_HMAC_SECRET", "")


# ──────────────────────────────────────────────────────────────────────
# Regulatory tables (IATA DGR 66th edition / ICAO TI 2025-2026)
# ──────────────────────────────────────────────────────────────────────

# 9 ICAO/IATA hazard classes (per UN Model Regulations + ICAO TI Pt 2)
ICAO_IATA_CLASSES = {
    "1": {"name": "Explosives", "divisions": ["1.1", "1.2", "1.3", "1.4", "1.5", "1.6"]},
    "2": {"name": "Gases", "divisions": ["2.1 Flammable", "2.2 Non-flammable", "2.3 Toxic"]},
    "3": {"name": "Flammable liquids", "divisions": []},
    "4": {"name": "Flammable solids / spontaneously combustible / water-reactive",
          "divisions": ["4.1", "4.2", "4.3"]},
    "5": {"name": "Oxidizing substances and organic peroxides", "divisions": ["5.1", "5.2"]},
    "6": {"name": "Toxic and infectious substances", "divisions": ["6.1 Toxic", "6.2 Infectious"]},
    "7": {"name": "Radioactive material", "divisions": []},
    "8": {"name": "Corrosives", "divisions": []},
    "9": {"name": "Miscellaneous DG (incl. lithium batteries, magnetised, ELT)", "divisions": []},
}

# Lithium-battery UN numbers (IATA DGR Table 4.2 + PIs 965-970)
LITHIUM_UN_NUMBERS = {
    "UN3480": {"label": "Lithium-ion batteries", "packed": "alone",
               "packing_instruction": "965", "class": "9"},
    "UN3481_with_equipment": {"label": "Lithium-ion batteries packed with equipment",
                              "packed": "with_equipment",
                              "packing_instruction": "966", "class": "9"},
    "UN3481_in_equipment": {"label": "Lithium-ion batteries contained in equipment",
                            "packed": "in_equipment",
                            "packing_instruction": "967", "class": "9"},
    "UN3090": {"label": "Lithium-metal batteries", "packed": "alone",
               "packing_instruction": "968", "class": "9"},
    "UN3091_with_equipment": {"label": "Lithium-metal batteries packed with equipment",
                              "packed": "with_equipment",
                              "packing_instruction": "969", "class": "9"},
    "UN3091_in_equipment": {"label": "Lithium-metal batteries contained in equipment",
                            "packed": "in_equipment",
                            "packing_instruction": "970", "class": "9"},
}

# PI 965 Section limits for Li-ion (alone) — per IATA DGR 66 (2025)
# Lithium-ion are FORBIDDEN on passenger aircraft when shipped alone (PI 965 IA/IB)
# Section II permits small batteries under stricter limits with carrier-permission
LI_ION_PI_SECTIONS = {
    "IA": {"max_wh_per_cell": ">20 Wh",
           "max_wh_per_battery": ">100 Wh",
           "max_per_package": "no limit (UN spec packaging)",
           "aircraft": "Cargo Aircraft Only (CAO)",
           "shippers_declaration": "Required",
           "spec_packaging": "UN spec (4G/4D/4H2 etc.) required"},
    "IB": {"max_wh_per_cell": "≤20 Wh",
           "max_wh_per_battery": "≤100 Wh",
           "max_per_package_kg": 10,
           "aircraft": "Cargo Aircraft Only (CAO)",
           "shippers_declaration": "Required",
           "spec_packaging": "UN spec required + 'Section IB' on label"},
    "II": {"max_wh_per_cell": "≤20 Wh",
           "max_wh_per_battery": "≤100 Wh",
           "max_cells_per_package": 8,
           "max_batteries_per_package": 2,
           "max_packages_per_consignment": 1,
           "aircraft": "Cargo Aircraft Only (CAO) effective Apr 2016",
           "shippers_declaration": "Not required (but lithium battery mark + handling label required)"},
}

# State of charge limit for Li-ion (PI 965 §II + IA/IB) — effective 1 Apr 2016
# All Li-ion cells/batteries shipped alone must be at ≤30% SoC
LI_ION_SOC_LIMIT_PCT = 30
LI_ION_SOC_BASIS = "IATA DGR PI 965 §IA/IB/II (effective 1 April 2016)"

# Cargo-Aircraft-Only items (sample — IATA DGR Table 4.2)
CAO_ONLY_UN_CODES = {
    "UN3480", "UN3090",          # Lithium batteries shipped alone
    "UN1942",                     # Ammonium nitrate
    "UN3170",                     # Aluminium smelting by-products
    "UN0144", "UN0210",          # Class 1 explosives (most)
    "UN1830",                     # Sulfuric acid
}

# UN packaging codes — IATA DGR §6 (single + combination)
UN_PACKAGING_CODES = {
    "1A1": "Steel drum, non-removable head",
    "1A2": "Steel drum, removable head",
    "1B1": "Aluminium drum, non-removable head",
    "1G":  "Fibre drum",
    "1H1": "Plastic drum, non-removable head",
    "1H2": "Plastic drum, removable head",
    "3H1": "Plastic jerrican, non-removable head",
    "3H2": "Plastic jerrican, removable head",
    "4G":  "Fibreboard box (cardboard)",
    "4D":  "Plywood box",
    "4C1": "Wooden box, ordinary",
    "4H1": "Expanded plastics box",
    "4H2": "Solid plastics box",
    "5H1": "Woven plastics bag, no liner",
    "5L1": "Textile bag, no liner",
    "6HA1": "Plastic + steel composite (jerrican-in-box)",
}

# UN spec packaging code regex: e.g. 4G/Y50/S/24/GB/123 (IATA §6.0.4)
UN_PACKAGING_CODE_RE = re.compile(
    r"^(?P<type>[1-6][A-H][A-Z]?\d?)/"
    r"(?P<pg>[XYZ])(?P<mass_or_density>\d+(?:\.\d+)?)/"
    r"(?P<solid_or_liquid>[SL])/"
    r"(?P<year>\d{2,4})/"
    r"(?P<country>[A-Z]{1,3})/"
    r"(?P<manufacturer>.+)$"
)

# State variations (a subset — IATA DGR §2.8 Significant Variations)
STATE_VARIATIONS = {
    "US": ["USG-01: 49 CFR 173.27 limits at US-airports",
           "USG-02: FAA marking + labelling stricter",
           "USG-13: Quarter-loading guidance for radioactives",
           "USG-19: Lithium battery telephone reporting under 49 CFR 171.15/171.16"],
    "GB": ["GBG-01: CAA UK CAP 1349 operator approvals",
           "GBG-03: Restricted ELT and PED batteries in checked baggage"],
    "DE": ["DEG-01: BAM-approved packagings only",
           "DEG-02: BAG written approval required for Class 1"],
    "FR": ["FRG-01: French civil aviation regulation arrêté DGCA"],
    "CN": ["CNG-01: CAAC operator approval for lithium battery imports",
           "CNG-02: MA written approval before shipment (Class 1, 7)"],
    "AE": ["AEG-01: GCAA approval for all DG to/from UAE"],
    "AU": ["AUG-01: CASA Part 92 — operator approval"],
    "CA": ["CAG-01: Transport Canada TDG approval + Class 7 doc",
           "CAG-04: Lithium battery quarter-loading"],
    "JP": ["JPG-01: JCAB Notification No 1226 + lithium quarter-loading"],
    "IN": ["ING-01: DGCA Civil Aviation Requirement Section 2 Series O Part VI"],
}

# Operator variations (each carrier may be MORE restrictive than IATA)
OPERATOR_VARIATIONS = {
    "fedex": ["FX-04: Section II Li-ion forbidden without prior carrier approval",
              "FX-12: Damaged/defective lithium batteries forbidden (UN3171 + UN3556 dam.)",
              "FX-21: Excepted lithium not accepted as freight without DGR-trained shipper"],
    "ups": ["5X-04: Section II Li-ion alone forbidden; pre-acceptance required",
            "5X-09: All damaged/defective batteries forbidden (no PI 965 §II)",
            "5X-15: UN3536 Li in cargo transport units only via UPS Air Freight"],
    "cathay": ["CX-02: Class 7 radioactive requires HKCAD pre-approval"],
    "emirates": ["EK-01: All lithium battery shipments require pre-acceptance",
                 "EK-04: Hidden DG screen at acceptance"],
    "dhl": ["DHL-03: Section II lithium accepted with DGR-trained shipper signoff",
            "DHL-08: Excepted Li-ion shipments scanned against IATA DGR 66"],
    "lufthansa": ["LH-01: Strict adherence to LBA-approved packaging only"],
    "qatar": ["QR-02: Damaged batteries forbidden (no exceptions)"],
}


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _sign(payload: dict) -> str:
    """HMAC-sign the response for tamper-evident audit."""
    if not _HMAC_SECRET:
        return "unsigned-no-key-configured"
    return hmac.new(
        _HMAC_SECRET.encode(),
        json.dumps(payload, sort_keys=True, default=str).encode(),
        hashlib.sha256,
    ).hexdigest()


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _attestation(payload: dict) -> dict:
    return {
        **payload,
        "ts": _ts(),
        "sig": _sign(payload),
        "issuer": "meok-iata-dgr-air-cargo-mcp",
        "version": "1.0.0",
    }


def _li_ion_section(wh_per_battery: float, wh_per_cell: float) -> str:
    """Map Wh ratings to PI 965 Section IA / IB / II."""
    if wh_per_cell > 20 or wh_per_battery > 100:
        return "IA"
    # ≤20 Wh per cell and ≤100 Wh per battery
    # Section II only if small quantity (otherwise IB)
    return "IB"


# ──────────────────────────────────────────────────────────────────────
# Tools
# ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def classify_air_dangerous_good(
    material_name: str,
    un_number: str = "",
    likely_class: str = "",
) -> dict:
    """Classify an air-cargo material against the 9 ICAO/IATA hazard classes.

    Args:
      material_name: free-text name (e.g. 'Lithium-ion battery pack')
      un_number: optional pre-known UN code (e.g. 'UN3480')
      likely_class: optional class string (e.g. '9')

    Returns:
      class details, applicable UN number(s), and air-transport guidance.
    """
    name = material_name.lower()
    cls = likely_class.strip() or ""
    un = un_number.strip().upper() or ""
    inferred_un = []

    # crude inference — caller should supply un_number for high-confidence
    if "lithium" in name and "ion" in name:
        if "alone" in name or "battery only" in name:
            inferred_un.append("UN3480")
        elif "in equipment" in name:
            inferred_un.append("UN3481_in_equipment")
        elif "with equipment" in name:
            inferred_un.append("UN3481_with_equipment")
        else:
            inferred_un.append("UN3480")
        cls = "9"
    elif "lithium" in name and "metal" in name:
        inferred_un.append("UN3090")
        cls = "9"
    elif "petrol" in name or "gasoline" in name:
        inferred_un.append("UN1203")
        cls = "3"
    elif "ammonium nitrate" in name:
        inferred_un.append("UN1942")
        cls = "5.1"
    elif "explosive" in name:
        cls = "1"
    elif "radioactive" in name:
        cls = "7"
    elif "acid" in name or "corrosive" in name:
        cls = "8"

    cls_key = cls.split(".")[0] if cls else ""
    cls_info = ICAO_IATA_CLASSES.get(cls_key, {})

    payload = {
        "tool": "classify_air_dangerous_good",
        "material_name": material_name,
        "classified_class": cls or "unknown — supply un_number",
        "class_name": cls_info.get("name", "unknown"),
        "class_divisions": cls_info.get("divisions", []),
        "supplied_un_number": un or None,
        "inferred_un_numbers": inferred_un,
        "is_lithium_battery": (cls == "9" and any("UN34" in u or "UN30" in u for u in inferred_un + [un])),
        "advisory": (
            "Lithium batteries: see check_lithium_battery_air_transport for PI 965-970 limits."
            if cls == "9" and inferred_un else
            "Verify against IATA DGR §4.2 (UN list) before booking carrier."
        ),
    }
    return _attestation(payload)


@mcp.tool()
def check_lithium_battery_air_transport(
    cell_wh: float,
    battery_wh: float,
    net_qty_kg: float,
    packed: str = "alone",
    is_damaged_or_defective: bool = False,
) -> dict:
    """Determine the correct UN code + Packing Instruction Section for Li-ion air freight.

    Args:
      cell_wh: watt-hour rating per cell
      battery_wh: watt-hour rating per battery (assembled)
      net_qty_kg: total net mass of batteries in the package (kg)
      packed: 'alone' / 'with_equipment' / 'in_equipment'
      is_damaged_or_defective: True if cells fall under IATA DGR §3.9.2.6 + Special Provision A154
    """
    if is_damaged_or_defective:
        return _attestation({
            "tool": "check_lithium_battery_air_transport",
            "forbidden": True,
            "reason": (
                "Damaged or defective lithium batteries are FORBIDDEN for air transport "
                "under IATA DGR Special Provision A154 / Operator Variation A201. "
                "Use ground/sea or specialised waste carrier instead."
            ),
            "applicable_provision": "A154 / A201",
        })

    # Determine UN number based on packaging context
    if packed == "alone":
        un = "UN3480"
        pi = "965"
    elif packed == "with_equipment":
        un = "UN3481"
        pi = "966"
    elif packed == "in_equipment":
        un = "UN3481"
        pi = "967"
    else:
        un = "UN3480"
        pi = "965"

    # Section selection (only PI 965 has IA/IB/II split — 966/967 use I/II)
    if packed == "alone":
        section = _li_ion_section(battery_wh, cell_wh)
        # PI 965 Section II permitted only for very small quantities AND single package
        # Switching to II if cells small AND tiny quantity
        if section == "IB" and net_qty_kg <= 5.0 and cell_wh <= 20 and battery_wh <= 100:
            # Caller can still choose Section II below
            section_advisory = "Section IB or II (II only for ≤8 cells / ≤2 batteries / 1 pkg)"
        else:
            section_advisory = section
    else:
        section = "I" if cell_wh > 20 or battery_wh > 100 else "II"
        section_advisory = section

    section_info = LI_ION_PI_SECTIONS.get(section, {})

    payload = {
        "tool": "check_lithium_battery_air_transport",
        "applicable_un_number": un,
        "packing_instruction": pi,
        "section": section,
        "section_advisory": section_advisory,
        "section_rules": section_info,
        "cell_wh": cell_wh,
        "battery_wh": battery_wh,
        "net_qty_kg": net_qty_kg,
        "packed": packed,
        "cargo_aircraft_only": True,
        "shippers_declaration_required": section in ("IA", "IB", "I"),
        "lithium_battery_mark_required": True,
        "soc_limit_pct": LI_ION_SOC_LIMIT_PCT if packed == "alone" else None,
        "advisory": (
            "Check carrier acceptance: many operators (FedEx FX-04, UPS 5X-04) "
            "forbid Section II Li-ion entirely."
        ),
    }
    return _attestation(payload)


@mcp.tool()
def check_state_of_charge_air(
    soc_pct: float,
    un_code: str = "UN3480",
    packed: str = "alone",
) -> dict:
    """Verify Li-ion State-of-Charge is ≤30% for air freight (PI 965).

    Args:
      soc_pct: state of charge 0-100
      un_code: UN number ('UN3480' / 'UN3481' / 'UN3090' / 'UN3091')
      packed: 'alone' / 'with_equipment' / 'in_equipment'
    """
    soc_rule_applies = un_code.startswith("UN3480") or (un_code.startswith("UN3481") and packed == "alone")

    if not soc_rule_applies:
        return _attestation({
            "tool": "check_state_of_charge_air",
            "soc_pct": soc_pct,
            "rule_applies": False,
            "advisory": (
                "30% SoC limit applies to UN3480 (Li-ion alone) and UN3481 packed alone. "
                "Batteries inside equipment (UN3481 in_equipment) may exceed 30% if rated ≤100 Wh."
            ),
        })

    compliant = soc_pct <= LI_ION_SOC_LIMIT_PCT
    payload = {
        "tool": "check_state_of_charge_air",
        "soc_pct": soc_pct,
        "soc_limit_pct": LI_ION_SOC_LIMIT_PCT,
        "rule_applies": True,
        "compliant": compliant,
        "un_code": un_code,
        "basis": LI_ION_SOC_BASIS,
        "advisory": (
            "OK — discharge to ≤30% before packaging." if compliant else
            f"NON-COMPLIANT — battery at {soc_pct}% exceeds {LI_ION_SOC_LIMIT_PCT}% limit. "
            f"Discharge before shipment or use ground/sea freight."
        ),
    }
    return _attestation(payload)


@mcp.tool()
def generate_iata_shippers_declaration(
    shipper_name: str,
    shipper_address: str,
    consignee_name: str,
    consignee_address: str,
    airport_of_departure: str,
    airport_of_destination: str,
    un_number: str,
    proper_shipping_name: str,
    hazard_class: str,
    packing_group: str = "",
    net_qty_per_package: str = "",
    number_of_packages: int = 1,
    packaging_type_code: str = "",
    packing_instruction: str = "",
    aircraft_limit: str = "Cargo Aircraft Only",
    emergency_contact_name: str = "",
    emergency_contact_phone: str = "",
    signature_name: str = "",
) -> dict:
    """Generate the IATA Shipper's Declaration for Dangerous Goods (IATA DGR §8).

    The Shipper's Declaration (formerly form 22-1) is mandatory for most DG.
    Two pink-striped originals must accompany the consignment.

    Args:
      Shipping party + addresses
      un_number: e.g. 'UN3480'
      proper_shipping_name: e.g. 'Lithium ion batteries'
      hazard_class: e.g. '9'
      packing_group: I / II / III / '' (n/a for lithium)
      net_qty_per_package: e.g. '10 kg' or '40 Wh'
      packaging_type_code: UN spec code (e.g. '4G')
      packing_instruction: '965', '966', '967', '968', '969', '970'
      aircraft_limit: 'Cargo Aircraft Only' or 'Passenger and Cargo Aircraft'
      emergency_contact_name + phone: 24-hour contact per IATA DGR §8.1.6.13
      signature_name: shipper's DGR-trained signatory
    """
    declaration = {
        "form_title": "Shipper's Declaration for Dangerous Goods",
        "form_basis": "IATA Dangerous Goods Regulations §8.1",
        "form_number_legacy": "22-1",
        "shipper": {"name": shipper_name, "address": shipper_address},
        "consignee": {"name": consignee_name, "address": consignee_address},
        "transport_details": {
            "airport_of_departure": airport_of_departure,
            "airport_of_destination": airport_of_destination,
            "aircraft_limit": aircraft_limit,
            "shipment_type": "Non-radioactive",
        },
        "nature_and_quantity_of_dangerous_goods": [
            {
                "un_or_id_number": un_number,
                "proper_shipping_name": proper_shipping_name,
                "class_or_division": hazard_class,
                "packing_group": packing_group or "n/a",
                "quantity_and_type_of_packing": (
                    f"{number_of_packages} x {packaging_type_code} package(s), "
                    f"net qty {net_qty_per_package}"
                ),
                "packing_instruction": packing_instruction,
                "authorization": f"per IATA DGR PI {packing_instruction}" if packing_instruction else "",
            }
        ],
        "additional_handling_information": (
            "All packages contain lithium batteries — emergency procedures per "
            "ICAO Doc 9481-AN/928 (ERG Manual)."
            if un_number.startswith(("UN3480", "UN3090", "UN3481", "UN3091")) else
            "Refer to IATA Emergency Response Drill Codes."
        ),
        "emergency_response_24h": {
            "name": emergency_contact_name,
            "phone": emergency_contact_phone,
        },
        "shipper_certification_text": (
            "I hereby declare that the contents of this consignment are fully "
            "and accurately described above by the proper shipping name, and "
            "are classified, packaged, marked and labelled/placarded, and are "
            "in all respects in proper condition for transport according to "
            "applicable international and national governmental regulations. "
            "I declare that all of the applicable air transport requirements "
            "have been met."
        ),
        "name_and_title_of_signatory": signature_name,
        "place_and_date": _ts(),
        "two_originals_required": True,
        "pink_diagonal_hatching_required": True,
        "issued_at": _ts(),
    }
    return _attestation({
        "tool": "generate_iata_shippers_declaration",
        "declaration": declaration,
    })


@mcp.tool()
def check_passenger_vs_cargo_aircraft(
    un_number: str,
    aircraft_type: str = "passenger",
) -> dict:
    """Check whether a UN material is permitted on passenger aircraft or Cargo-Aircraft-Only (CAO).

    Args:
      un_number: e.g. 'UN3480'
      aircraft_type: 'passenger' / 'cargo' / 'mixed'
    """
    un = un_number.strip().upper()
    cao_required = un in CAO_ONLY_UN_CODES

    # PI 965-970 specifics
    li_battery_cao = un.startswith(("UN3480", "UN3090"))

    if aircraft_type == "passenger" and (cao_required or li_battery_cao):
        permitted = False
        reason = (
            f"{un} is Cargo Aircraft Only — passenger aircraft transport forbidden. "
            "Use a freighter (CAO) operator only."
        )
    else:
        permitted = True
        reason = f"{un} acceptable on {aircraft_type} aircraft subject to PI limits."

    payload = {
        "tool": "check_passenger_vs_cargo_aircraft",
        "un_number": un,
        "aircraft_type_requested": aircraft_type,
        "cargo_aircraft_only_required": cao_required or li_battery_cao,
        "permitted_on_requested_aircraft": permitted,
        "reason": reason,
        "cao_label_required": cao_required or li_battery_cao,
        "advisory": (
            "Apply Cargo Aircraft Only label (orange/black) per IATA DGR §7.2.7.1 "
            "to ALL packages when CAO."
        ) if (cao_required or li_battery_cao) else None,
    }
    return _attestation(payload)


@mcp.tool()
def validate_un_specification_packaging(
    packaging_code: str,
) -> dict:
    """Validate a UN specification packaging marking string (e.g. '4G/Y50/S/24/GB/MeokAcme-987').

    Format per IATA DGR §6.0.4:
      <type><material> / <PG><gross-mass-or-density> / <S-or-L> / <year> / <state> / <manufacturer>

    Args:
      packaging_code: the full UN spec marking as moulded/printed on the packaging
    """
    code = packaging_code.strip()
    m = UN_PACKAGING_CODE_RE.match(code)

    if not m:
        return _attestation({
            "tool": "validate_un_specification_packaging",
            "packaging_code": code,
            "valid_format": False,
            "advisory": (
                "Marking does not match IATA DGR §6.0.4 format: "
                "<type>/<PG><mass>/<S|L>/<year>/<state>/<manuf>. "
                "Examples: 4G/Y50/S/24/GB/MeokAcme-987"
            ),
        })

    fields = m.groupdict()
    type_code = fields["type"].upper()
    type_label = UN_PACKAGING_CODES.get(type_code, f"Unknown code '{type_code}'")
    pg_map = {"X": "I", "Y": "II", "Z": "III"}
    payload = {
        "tool": "validate_un_specification_packaging",
        "packaging_code": code,
        "valid_format": True,
        "type_code": type_code,
        "type_description": type_label,
        "packing_group_letter": fields["pg"],
        "packing_group_roman": pg_map[fields["pg"]],
        "max_gross_mass_kg_or_density": fields["mass_or_density"],
        "solid_or_liquid": fields["solid_or_liquid"],
        "year_of_manufacture": fields["year"],
        "country_code": fields["country"],
        "manufacturer_identifier": fields["manufacturer"],
        "advisory": (
            f"Type {type_code} = {type_label}. PG {pg_map[fields['pg']]}. "
            "Verify combination packaging includes UN inner-packaging spec."
        ),
    }
    return _attestation(payload)


@mcp.tool()
def check_country_variations(
    un_number: str,
    route_countries: list,
    operators: Optional[list] = None,
) -> dict:
    """Return applicable State + Operator variations for a route + carrier.

    Args:
      un_number: e.g. 'UN3480'
      route_countries: ISO-2 codes (e.g. ['GB','US','CN'])
      operators: optional list of carrier codes (e.g. ['fedex','ups'])
    """
    operators = operators or []
    state_hits = {}
    for c in route_countries:
        c_up = c.strip().upper()
        if c_up in STATE_VARIATIONS:
            state_hits[c_up] = STATE_VARIATIONS[c_up]

    operator_hits = {}
    for op in operators:
        op_l = op.strip().lower()
        if op_l in OPERATOR_VARIATIONS:
            operator_hits[op_l] = OPERATOR_VARIATIONS[op_l]

    # Lithium-battery special: virtually every major operator restricts it more than IATA
    li_warning = None
    if un_number.upper().startswith(("UN3480", "UN3090", "UN3481", "UN3091")):
        li_warning = (
            "Lithium batteries: most carriers (FedEx FX-04, UPS 5X-04, Emirates EK-01) "
            "require PRE-acceptance approval beyond standard IATA DGR §8 Shipper's Declaration."
        )

    payload = {
        "tool": "check_country_variations",
        "un_number": un_number,
        "route_countries": route_countries,
        "operators": operators,
        "state_variations_hit": state_hits,
        "operator_variations_hit": operator_hits,
        "lithium_specific_warning": li_warning,
        "advisory": (
            "ALWAYS check IATA DGR §2.8 (State Variations) and §2.9 (Operator Variations) "
            "before tendering — these override the base DGR rules."
        ),
    }
    return _attestation(payload)


@mcp.tool()
def prepare_iata_acceptance_check(
    air_waybill_number: str,
    un_number: str,
    proper_shipping_name: str,
    hazard_class: str,
    number_of_packages: int,
    packaging_type_code: str,
    packing_instruction: str,
    aircraft_type: str = "cargo",
    shippers_declaration_attached: bool = True,
    lithium_battery_mark_present: bool = False,
    cao_label_present: bool = False,
    handling_label_class_present: bool = False,
    overpack_marked: bool = False,
    package_external_damage: bool = False,
) -> dict:
    """Prepare the IATA DGR §9 Acceptance Check for a carrier (cargo handling agent).

    The acceptance checklist (DGR §9 Form 9.1.A) must be completed by the
    carrier or its agent before a DG consignment is loaded on aircraft.

    Args:
      Standard AWB + UN/class fields + per-package check items
    """
    findings = []

    # Documentation
    if not shippers_declaration_attached:
        findings.append("§9.1.A item 1: Shipper's Declaration MISSING — REJECT")

    # Lithium-battery handling
    is_lithium = un_number.upper().startswith(("UN3480", "UN3090", "UN3481", "UN3091"))
    if is_lithium and not lithium_battery_mark_present:
        findings.append("§9.1.A: Lithium-battery handling mark MISSING (UN3480 etc.) — REJECT")

    # CAO label
    cao_required = un_number.upper() in CAO_ONLY_UN_CODES or (
        is_lithium and un_number.upper().startswith(("UN3480", "UN3090"))
    )
    if cao_required and not cao_label_present:
        findings.append("§9.1.A: Cargo Aircraft Only label MISSING — REJECT")
    if cao_required and aircraft_type == "passenger":
        findings.append("§9.1.A: CAO-only good loaded on passenger aircraft — REJECT")

    # Class hazard label
    if not handling_label_class_present:
        findings.append(f"§9.1.A: Class {hazard_class} hazard label MISSING — REJECT")

    # Damage
    if package_external_damage:
        findings.append("§9.1.A item 11: External package damage — REJECT")

    # Per-package marking
    if not packaging_type_code:
        findings.append("§9.1.A item 9: UN spec packaging code missing on package — REVIEW")

    accepted = len(findings) == 0
    payload = {
        "tool": "prepare_iata_acceptance_check",
        "air_waybill_number": air_waybill_number,
        "un_number": un_number,
        "proper_shipping_name": proper_shipping_name,
        "hazard_class": hazard_class,
        "number_of_packages": number_of_packages,
        "packing_instruction": packing_instruction,
        "aircraft_type": aircraft_type,
        "checked_items": {
            "shippers_declaration_attached": shippers_declaration_attached,
            "lithium_battery_mark_present": lithium_battery_mark_present,
            "cao_label_present": cao_label_present,
            "class_hazard_label_present": handling_label_class_present,
            "overpack_marked": overpack_marked,
            "external_damage_observed": package_external_damage,
        },
        "findings": findings,
        "acceptance_decision": "ACCEPT" if accepted else "REJECT",
        "iata_form_basis": "IATA DGR §9.1.A — Dangerous Goods Acceptance Checklist",
        "advisory": (
            "Acceptance OK — issue NOTOC to PIC per IATA DGR §9.5 before loading."
            if accepted else
            "REJECT consignment, notify shipper, retain documentation."
        ),
    }
    return _attestation(payload)


# ──────────────────────────────────────────────────────────────────────
# Server entry
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()


# ── MEOK monetization layer (Stripe upgrade · PAYG · pricing) ──────────
# Free tier is zero-config. Upgrade to Pro (unlimited) or pay-as-you-go per call.
import os as _meok_os
MEOK_STRIPE_UPGRADE = "https://buy.stripe.com/00wfZjcgAeUW4c5cyQ8k90K"  # Pro (unlimited)
MEOK_PAYG_KEY = _meok_os.environ.get("MEOK_PAYG_KEY", "")  # set to enable PAYG (x402 / ~GBP0.05 per call)
MEOK_PRICING = "https://meok.ai/pricing"


def meok_upsell(tier: str = "free") -> dict:
    """Monetization options for free-tier callers: Pro upgrade, PAYG, or pricing page."""
    if tier != "free":
        return {}
    return {"upgrade_url": MEOK_STRIPE_UPGRADE,
            "payg_enabled": bool(MEOK_PAYG_KEY),
            "pricing": MEOK_PRICING}
