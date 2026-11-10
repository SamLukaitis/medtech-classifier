"""Tests for the clause-level audit trail, the Rule 13/15 corrections, the
regulatory pathway module and the class-driver analysis."""

from __future__ import annotations

from regulatory_pathway import build_pathway
from rules_engine.eu_mdr import EUMDRClassificationEngine
from rules_engine.models import (
    ActiveDeviceType,
    DeviceAttributes,
    DeviceClass,
    Duration,
    Invasiveness,
    TissueOrigin,
)
from rules_engine.sensitivity import class_drivers

ENGINE = EUMDRClassificationEngine()


def _outcome(device, rule_id):
    return next(o for o in ENGINE.classify(device).all_rule_outcomes if o.rule_id == rule_id)


def _pathway(device):
    result = ENGINE.classify(device)
    return result, {i.item_id: i for i in build_pathway(device, result)}


# --- Rule 15: "implantable or long term invasive devices" ---------------------


def test_rule15_intrauterine_device_is_class_iii():
    """An IUD is invasive via a body orifice (not surgically) and long-term.
    The rule text says 'long term invasive', so it is Class III."""
    iud = DeviceAttributes(
        invasiveness=Invasiveness.INVASIVE_BODY_ORIFICE,
        duration=Duration.LONG_TERM,
        is_contraceptive_or_sti_prevention=True,
    )
    assert _outcome(iud, "Rule 15").device_class == DeviceClass.III
    assert ENGINE.classify(iud).device_class == DeviceClass.III


def test_rule15_short_term_invasive_contraceptive_stays_iib():
    diaphragm = DeviceAttributes(
        invasiveness=Invasiveness.INVASIVE_BODY_ORIFICE,
        duration=Duration.SHORT_TERM,
        is_contraceptive_or_sti_prevention=True,
    )
    assert _outcome(diaphragm, "Rule 15").device_class == DeviceClass.IIB


# --- Rule 13: every active device not classified by Rules 9-12 ----------------


def test_rule13_catches_active_diagnostic_device_matching_no_rule10_indent():
    device = DeviceAttributes(is_active=True, active_type=ActiveDeviceType.DIAGNOSTIC_MONITORING)
    assert _outcome(device, "Rule 10").device_class is None
    assert _outcome(device, "Rule 13").device_class == DeviceClass.I


def test_rule13_does_not_apply_when_rule_9_to_12_classifies():
    pump = DeviceAttributes(
        is_active=True, active_type=ActiveDeviceType.OTHER_ACTIVE, administers_or_removes_substances_to_from_body=True
    )
    assert _outcome(pump, "Rule 12").device_class == DeviceClass.IIA
    assert _outcome(pump, "Rule 13").applies is False
    software = DeviceAttributes(is_active=True, is_software=True)
    assert _outcome(software, "Rule 13").applies is False


def test_rule13_does_not_apply_to_non_active_devices():
    assert _outcome(DeviceAttributes(), "Rule 13").applies is False


# --- clause-level audit trail ---------------------------------------------------


def test_matched_clause_names_the_deciding_exception():
    hip = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.LONG_TERM, is_implantable=True, is_joint_replacement=True
    )
    assert _outcome(hip, "Rule 8").matched_clauses == ["is a total or partial joint replacement"]


def test_matched_clause_falls_back_to_general_rule():
    plate = DeviceAttributes(invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.LONG_TERM, is_implantable=True)
    assert _outcome(plate, "Rule 8").matched_clauses == ["general rule for implantable and long-term surgically invasive devices"]


def test_matched_clauses_only_list_clauses_at_the_winning_class():
    laser = DeviceAttributes(
        is_active=True,
        active_type=ActiveDeviceType.THERAPEUTIC,
        administers_or_exchanges_energy=True,
        energy_exchange_potentially_hazardous=True,
    )
    outcome = _outcome(laser, "Rule 9")
    assert outcome.device_class == DeviceClass.IIB
    assert outcome.matched_clauses == ["may administer or exchange energy in a potentially hazardous way"]


def test_non_applicable_rule_has_no_clauses():
    assert _outcome(DeviceAttributes(), "Rule 8").matched_clauses == []


# --- regulatory pathway -----------------------------------------------------------


def test_class_i_is_self_declared_with_pms_report():
    result, p = _pathway(DeviceAttributes())
    assert result.device_class == DeviceClass.I
    assert "Self-declaration" in p["conformity_route"].summary
    assert p["notified_body"].summary == "None"
    assert "Article 85" in p["post_market_reporting"].citation
    assert not p["sscp"].applies and not p["implant_card"].applies


def test_class_i_sterile_measuring_gets_limited_notified_body():
    result, p = _pathway(DeviceAttributes(placed_on_market_sterile=True, has_measuring_function=True))
    assert [q.value for q in result.qualifiers] == ["Is", "Im"]
    assert "sterile conditions" in p["conformity_route"].summary
    assert "metrological" in p["conformity_route"].summary
    assert p["notified_body"].summary.startswith("Limited")


def test_class_iia_psur_every_two_years():
    device = DeviceAttributes(invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.TRANSIENT)
    result, p = _pathway(device)
    assert result.device_class == DeviceClass.IIA
    assert "every two years" in p["post_market_reporting"].summary
    assert "per device category" in p["conformity_route"].summary


def test_class_iib_implant_assessed_per_device_unless_exempt_type():
    plate = DeviceAttributes(invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.LONG_TERM, is_implantable=True)
    result, p = _pathway(plate)
    assert result.device_class == DeviceClass.IIB
    assert "for every device" in p["conformity_route"].summary
    assert p["implant_card"].applies and p["sscp"].applies and p["clinical_investigation"].applies
    assert not p["clinical_evaluation_consultation"].applies

    screw = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE,
        duration=Duration.LONG_TERM,
        is_implantable=True,
        is_joint_replacement=True,
        is_ancillary_component=True,
    )
    result, p = _pathway(screw)
    assert result.device_class == DeviceClass.IIB
    assert "generic device group" in p["conformity_route"].summary
    assert "screws" in p["conformity_route"].caveat


def test_class_iii_implant_triggers_expert_panel_and_annual_psur():
    hip = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.LONG_TERM, is_implantable=True, is_joint_replacement=True
    )
    result, p = _pathway(hip)
    assert result.device_class == DeviceClass.III
    assert p["clinical_evaluation_consultation"].applies
    assert "annually" in p["post_market_reporting"].summary and "EUDAMED" in p["post_market_reporting"].summary
    assert "every device" in p["conformity_route"].summary


def test_class_iib_active_drug_delivery_triggers_expert_panel_with_caveat():
    pump = DeviceAttributes(
        is_active=True,
        active_type=ActiveDeviceType.THERAPEUTIC,
        administers_or_removes_substances_to_from_body=True,
        administration_or_removal_potentially_hazardous=True,
    )
    result, p = _pathway(pump)
    assert result.device_class == DeviceClass.IIB
    assert p["clinical_evaluation_consultation"].applies
    assert "medicinal product" in p["clinical_evaluation_consultation"].caveat


def test_special_consultations():
    stent = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE, duration=Duration.LONG_TERM, is_implantable=True, contains_ancillary_medicinal_substance=True
    )
    _, p = _pathway(stent)
    assert p["medicinal_substance_consultation"].applies

    valve = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE,
        duration=Duration.LONG_TERM,
        is_implantable=True,
        contains_human_or_animal_tissue_or_cells=True,
        tissue_origin=TissueOrigin.ANIMAL,
    )
    _, p = _pathway(valve)
    assert p["tissue_consultation"].applies and "722/2012" in p["tissue_consultation"].summary

    leather = DeviceAttributes(
        contains_human_or_animal_tissue_or_cells=True, tissue_origin=TissueOrigin.ANIMAL, tissue_contacts_intact_skin_only=True
    )
    _, p = _pathway(leather)
    assert not p["tissue_consultation"].applies


def test_no_pathway_without_a_class():
    device = DeviceAttributes(invasiveness=Invasiveness.SURGICALLY_INVASIVE)  # no duration, so no rule fires
    result = ENGINE.classify(device)
    assert result.device_class is None
    assert build_pathway(device, result) == []


# --- class drivers ------------------------------------------------------------------


def test_drivers_identify_the_attribute_holding_the_class_up():
    hip = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE,
        duration=Duration.LONG_TERM,
        is_implantable=True,
        is_joint_replacement=True,
        placed_on_market_sterile=True,
    )
    drivers = {d.attribute: d.class_without for d in class_drivers(hip, ENGINE)}
    assert drivers["is_joint_replacement"] == "IIb"
    assert "placed_on_market_sterile" not in drivers  # sterility doesn't change a Class III result


def test_drivers_empty_when_two_independent_rules_give_the_same_class():
    stent = DeviceAttributes(
        invasiveness=Invasiveness.SURGICALLY_INVASIVE,
        duration=Duration.LONG_TERM,
        is_implantable=True,
        contacts_heart_or_central_circulatory_system=True,
        contains_ancillary_medicinal_substance=True,
    )
    assert class_drivers(stent, ENGINE) == []


def test_no_drivers_for_default_device():
    assert class_drivers(DeviceAttributes(), ENGINE) == []
