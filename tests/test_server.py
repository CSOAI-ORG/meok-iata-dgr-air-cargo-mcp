"""Smoke tests for meok-iata-dgr-air-cargo-mcp."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import (
    classify_air_dangerous_good,
    check_lithium_battery_air_transport,
    check_state_of_charge_air,
    generate_iata_shippers_declaration,
    check_passenger_vs_cargo_aircraft,
    validate_un_specification_packaging,
    check_country_variations,
    prepare_iata_acceptance_check,
    ICAO_IATA_CLASSES,
    LITHIUM_UN_NUMBERS,
    LI_ION_PI_SECTIONS,
    LI_ION_SOC_LIMIT_PCT,
    CAO_ONLY_UN_CODES,
    UN_PACKAGING_CODES,
    STATE_VARIATIONS,
    OPERATOR_VARIATIONS,
)


def _call(tool, **kwargs):
    """FastMCP wraps tools as Tool objects — extract the callable."""
    fn = tool.fn if hasattr(tool, "fn") else tool
    return fn(**kwargs)


# ──────────────────────────────────────────────────────────────────────
# classify_air_dangerous_good
# ──────────────────────────────────────────────────────────────────────

def test_classify_lithium_ion_battery_returns_class_9():
    r = _call(classify_air_dangerous_good,
              material_name="Lithium ion battery pack 18650 alone")
    assert r["classified_class"] == "9"
    assert "UN3480" in r["inferred_un_numbers"]
    assert r["is_lithium_battery"] is True


def test_classify_lithium_metal_returns_un3090():
    r = _call(classify_air_dangerous_good,
              material_name="Lithium metal coin cell battery")
    assert r["classified_class"] == "9"
    assert "UN3090" in r["inferred_un_numbers"]


def test_classify_explicit_un_number_passthrough():
    r = _call(classify_air_dangerous_good,
              material_name="Unknown chemistry pack",
              un_number="UN3480",
              likely_class="9")
    assert r["supplied_un_number"] == "UN3480"
    assert r["class_name"].startswith("Miscellaneous")


# ──────────────────────────────────────────────────────────────────────
# check_lithium_battery_air_transport
# ──────────────────────────────────────────────────────────────────────

def test_lithium_section_ia_for_large_battery():
    r = _call(check_lithium_battery_air_transport,
              cell_wh=25.0,
              battery_wh=300.0,
              net_qty_kg=20.0,
              packed="alone")
    assert r["section"] == "IA"
    assert r["applicable_un_number"] == "UN3480"
    assert r["packing_instruction"] == "965"
    assert r["cargo_aircraft_only"] is True
    assert r["shippers_declaration_required"] is True


def test_lithium_section_ib_for_small_battery():
    r = _call(check_lithium_battery_air_transport,
              cell_wh=10.0,
              battery_wh=80.0,
              net_qty_kg=4.0,
              packed="alone")
    assert r["section"] == "IB"


def test_lithium_damaged_is_forbidden():
    r = _call(check_lithium_battery_air_transport,
              cell_wh=10.0,
              battery_wh=80.0,
              net_qty_kg=4.0,
              packed="alone",
              is_damaged_or_defective=True)
    assert r["forbidden"] is True
    assert "A154" in r["applicable_provision"]


def test_lithium_in_equipment_uses_pi_967():
    r = _call(check_lithium_battery_air_transport,
              cell_wh=5.0,
              battery_wh=40.0,
              net_qty_kg=2.0,
              packed="in_equipment")
    assert r["applicable_un_number"] == "UN3481"
    assert r["packing_instruction"] == "967"


# ──────────────────────────────────────────────────────────────────────
# check_state_of_charge_air
# ──────────────────────────────────────────────────────────────────────

def test_soc_30pct_compliant():
    r = _call(check_state_of_charge_air, soc_pct=30.0, un_code="UN3480")
    assert r["compliant"] is True
    assert r["soc_limit_pct"] == LI_ION_SOC_LIMIT_PCT


def test_soc_50pct_non_compliant():
    r = _call(check_state_of_charge_air, soc_pct=50.0, un_code="UN3480")
    assert r["compliant"] is False
    assert "NON-COMPLIANT" in r["advisory"]


def test_soc_rule_does_not_apply_in_equipment():
    r = _call(check_state_of_charge_air,
              soc_pct=80.0,
              un_code="UN3481",
              packed="in_equipment")
    assert r["rule_applies"] is False


# ──────────────────────────────────────────────────────────────────────
# generate_iata_shippers_declaration
# ──────────────────────────────────────────────────────────────────────

def test_generate_shippers_declaration_for_un3480():
    r = _call(generate_iata_shippers_declaration,
              shipper_name="Acme Forwarders",
              shipper_address="Heathrow, UK",
              consignee_name="Tesla Service NJ",
              consignee_address="Springfield, NJ, USA",
              airport_of_departure="LHR",
              airport_of_destination="JFK",
              un_number="UN3480",
              proper_shipping_name="Lithium ion batteries",
              hazard_class="9",
              net_qty_per_package="10 kg",
              number_of_packages=2,
              packaging_type_code="4G",
              packing_instruction="965",
              emergency_contact_name="DGR Hotline",
              emergency_contact_phone="+44 1234 567890",
              signature_name="J. Smith DGR")
    decl = r["declaration"]
    assert decl["form_basis"].startswith("IATA Dangerous Goods Regulations §8")
    assert decl["transport_details"]["airport_of_departure"] == "LHR"
    assert decl["nature_and_quantity_of_dangerous_goods"][0]["un_or_id_number"] == "UN3480"
    assert decl["two_originals_required"] is True
    assert decl["pink_diagonal_hatching_required"] is True


# ──────────────────────────────────────────────────────────────────────
# check_passenger_vs_cargo_aircraft
# ──────────────────────────────────────────────────────────────────────

def test_un3480_on_passenger_aircraft_forbidden():
    r = _call(check_passenger_vs_cargo_aircraft,
              un_number="UN3480",
              aircraft_type="passenger")
    assert r["permitted_on_requested_aircraft"] is False
    assert r["cargo_aircraft_only_required"] is True


def test_un3480_on_cargo_aircraft_permitted():
    r = _call(check_passenger_vs_cargo_aircraft,
              un_number="UN3480",
              aircraft_type="cargo")
    assert r["permitted_on_requested_aircraft"] is True
    assert r["cao_label_required"] is True


# ──────────────────────────────────────────────────────────────────────
# validate_un_specification_packaging
# ──────────────────────────────────────────────────────────────────────

def test_valid_un_packaging_4g_parses():
    r = _call(validate_un_specification_packaging,
              packaging_code="4G/Y50/S/24/GB/MeokAcme-987")
    assert r["valid_format"] is True
    assert r["type_code"] == "4G"
    assert r["packing_group_roman"] == "II"
    assert r["country_code"] == "GB"
    assert "Fibreboard" in r["type_description"]


def test_invalid_un_packaging_rejected():
    r = _call(validate_un_specification_packaging,
              packaging_code="GARBAGE-CODE-123")
    assert r["valid_format"] is False
    assert "does not match" in r["advisory"]


# ──────────────────────────────────────────────────────────────────────
# check_country_variations
# ──────────────────────────────────────────────────────────────────────

def test_country_variations_lhr_jfk_fedex_lithium():
    r = _call(check_country_variations,
              un_number="UN3480",
              route_countries=["GB", "US"],
              operators=["fedex"])
    assert "GB" in r["state_variations_hit"]
    assert "US" in r["state_variations_hit"]
    assert "fedex" in r["operator_variations_hit"]
    assert r["lithium_specific_warning"] is not None


def test_country_variations_non_lithium_no_warning():
    r = _call(check_country_variations,
              un_number="UN1203",
              route_countries=["DE"],
              operators=[])
    assert r["lithium_specific_warning"] is None
    assert "DE" in r["state_variations_hit"]


# ──────────────────────────────────────────────────────────────────────
# prepare_iata_acceptance_check
# ──────────────────────────────────────────────────────────────────────

def test_acceptance_check_full_pass():
    r = _call(prepare_iata_acceptance_check,
              air_waybill_number="125-12345678",
              un_number="UN3480",
              proper_shipping_name="Lithium ion batteries",
              hazard_class="9",
              number_of_packages=1,
              packaging_type_code="4G",
              packing_instruction="965",
              aircraft_type="cargo",
              shippers_declaration_attached=True,
              lithium_battery_mark_present=True,
              cao_label_present=True,
              handling_label_class_present=True)
    assert r["acceptance_decision"] == "ACCEPT"
    assert r["findings"] == []


def test_acceptance_check_missing_cao_rejects():
    r = _call(prepare_iata_acceptance_check,
              air_waybill_number="125-99999999",
              un_number="UN3480",
              proper_shipping_name="Lithium ion batteries",
              hazard_class="9",
              number_of_packages=1,
              packaging_type_code="4G",
              packing_instruction="965",
              aircraft_type="cargo",
              shippers_declaration_attached=True,
              lithium_battery_mark_present=True,
              cao_label_present=False,
              handling_label_class_present=True)
    assert r["acceptance_decision"] == "REJECT"
    assert any("CAO" in f or "Cargo Aircraft Only" in f for f in r["findings"])


def test_acceptance_check_damage_rejects():
    r = _call(prepare_iata_acceptance_check,
              air_waybill_number="125-44444444",
              un_number="UN3480",
              proper_shipping_name="Lithium ion batteries",
              hazard_class="9",
              number_of_packages=2,
              packaging_type_code="4G",
              packing_instruction="965",
              aircraft_type="cargo",
              shippers_declaration_attached=True,
              lithium_battery_mark_present=True,
              cao_label_present=True,
              handling_label_class_present=True,
              package_external_damage=True)
    assert r["acceptance_decision"] == "REJECT"
    assert any("damage" in f.lower() for f in r["findings"])


# ──────────────────────────────────────────────────────────────────────
# Attestation + tables
# ──────────────────────────────────────────────────────────────────────

def test_attestation_carries_ts_sig_issuer():
    r = _call(classify_air_dangerous_good, material_name="lithium ion battery")
    assert "ts" in r and "sig" in r and "issuer" in r
    assert r["issuer"] == "meok-iata-dgr-air-cargo-mcp"
    assert r["version"] == "1.0.0"


def test_hmac_signature_when_secret_set(monkeypatch):
    import server as srv
    monkeypatch.setattr(srv, "_HMAC_SECRET", "test-secret-key")
    payload = {"a": 1, "b": "two"}
    sig = srv._sign(payload)
    assert sig != "unsigned-no-key-configured"
    assert len(sig) == 64  # sha256 hex


def test_hmac_signature_unsigned_without_secret(monkeypatch):
    import server as srv
    monkeypatch.setattr(srv, "_HMAC_SECRET", "")
    sig = srv._sign({"x": 1})
    assert sig == "unsigned-no-key-configured"


def test_icao_classes_complete():
    assert set(ICAO_IATA_CLASSES.keys()) == {"1", "2", "3", "4", "5", "6", "7", "8", "9"}


def test_lithium_un_table_has_all_codes():
    assert "UN3480" in LITHIUM_UN_NUMBERS
    assert "UN3090" in LITHIUM_UN_NUMBERS
    assert LITHIUM_UN_NUMBERS["UN3480"]["packing_instruction"] == "965"
    assert LITHIUM_UN_NUMBERS["UN3090"]["packing_instruction"] == "968"


def test_pi_965_section_table_complete():
    assert {"IA", "IB", "II"} <= set(LI_ION_PI_SECTIONS.keys())


def test_cao_only_codes_include_lithium():
    assert "UN3480" in CAO_ONLY_UN_CODES
    assert "UN3090" in CAO_ONLY_UN_CODES


def test_un_packaging_codes_table():
    assert "4G" in UN_PACKAGING_CODES
    assert "Fibreboard" in UN_PACKAGING_CODES["4G"]


def test_state_variations_has_uk_us():
    assert "US" in STATE_VARIATIONS
    assert "GB" in STATE_VARIATIONS


def test_operator_variations_has_fedex_ups():
    assert "fedex" in OPERATOR_VARIATIONS
    assert "ups" in OPERATOR_VARIATIONS


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
