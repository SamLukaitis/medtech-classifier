/*
 * EU MDR 2017/745 Annex VIII classifier - browser port.
 *
 * A line-for-line JavaScript port of rules_engine/eu_mdr/rules.py, engine.py,
 * rules_engine/sensitivity.py, regulatory_pathway/eu_mdr.py and
 * standards_mapper/eu_mdr/requirements.py, so the portfolio demo still
 * works with no server. tests/test_js_parity.py runs this file under Node
 * against thousands of random devices and requires identical results to the
 * Python engine (class, qualifiers, every rule's outcome and deciding clause,
 * applicable GSPRs and standards, regulatory pathway and class drivers). Change the Python first, then this file, then rerun that test.
 *
 * Educational demo only - not regulatory advice.
 */
(function (root) {
  "use strict";

  var RANK = { I: 0, IIa: 1, IIb: 2, III: 3 };
  var SRC = "Regulation (EU) 2017/745, Annex VIII, Chapter III";

  var DEFAULTS = {
    name: "",
    invasiveness: "non_invasive",
    duration: "not_applicable",
    is_implantable: false,
    is_active: false,
    active_type: "not_active",
    is_software: false,
    drives_or_influences_device_class: null,
    placed_on_market_sterile: false,
    has_measuring_function: false,
    is_reusable_surgical_instrument: false,
    body_orifice_site: "not_applicable",
    liable_to_be_absorbed_by_mucous_membrane: false,
    connected_to_active_device_class: null,
    contacts_heart_or_central_circulatory_system: false,
    contacts_central_nervous_system: false,
    placed_in_teeth: false,
    is_spinal_disc_replacement_or_contacts_spinal_column: false,
    is_joint_replacement: false,
    is_breast_implant_or_surgical_mesh: false,
    is_active_implantable_or_accessory: false,
    is_ancillary_component: false,
    supplies_ionising_radiation: false,
    has_biological_effect_or_wholly_mainly_absorbed: false,
    undergoes_chemical_change_in_body: false,
    administers_medicinal_product: false,
    administration_potentially_hazardous: false,
    channels_or_stores_for_infusion_administration_or_introduction: false,
    storage_target: "none",
    modifies_biological_or_chemical_composition: false,
    modification_treatment_type: "none",
    in_vitro_direct_contact_with_cells_tissues_organs_or_embryos: false,
    contacts_injured_skin_or_mucous_membrane: false,
    wound_contact_purpose: "none",
    administers_or_exchanges_energy: false,
    energy_exchange_potentially_hazardous: false,
    controls_monitors_or_influences_therapeutic_class_iib_device: false,
    emits_ionising_radiation_therapeutic: false,
    emits_ionising_radiation_diagnostic_or_interventional: false,
    controls_monitors_or_influences_active_implantable_device: false,
    diagnostic_supplies_energy_absorbed_by_body: false,
    diagnostic_illuminates_patient_visible_spectrum_only: false,
    diagnostic_images_in_vivo_radiopharmaceutical_distribution: false,
    diagnostic_allows_direct_diagnosis_or_monitoring_of_vital_physiological_processes: false,
    diagnostic_variation_could_cause_immediate_danger: false,
    software_decision_impact: "not_applicable",
    software_monitors_physiological_processes: false,
    software_monitors_vital_parameters_with_immediate_danger_potential: false,
    administers_or_removes_substances_to_from_body: false,
    administration_or_removal_potentially_hazardous: false,
    contains_ancillary_medicinal_substance: false,
    is_contraceptive_or_sti_prevention: false,
    disinfect_clean_target: "none",
    is_xray_diagnostic_image_recording_device: false,
    contains_human_or_animal_tissue_or_cells: false,
    tissue_origin: "none",
    tissue_contacts_intact_skin_only: false,
    contains_nanomaterial: false,
    nanomaterial_internal_exposure_potential: "none",
    administers_medicinal_product_by_inhalation: false,
    inhalation_essential_impact_or_life_threatening: false,
    composed_of_substances_absorbed_or_dispersed_via_orifice_or_skin: false,
    systemically_absorbed: false,
    achieves_purpose_in_stomach_or_lower_gi_tract: false,
    applied_to_skin_or_nasal_oral_cavity_to_pharynx: false,
    is_active_therapeutic_with_integrated_diagnostic_function: false,
  };

  function highest(list) {
    var best = null;
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if (c != null && (best == null || RANK[c] > RANK[best])) best = c;
    }
    return best;
  }

  // Annex VIII 3.5: among matched candidates, the highest class wins.
  // Clause wording for the rule being evaluated; picked up (and cleared) by out().
  var pendingClauses = [];
  function clausesAt(list, cls) {
    var seen = [];
    for (var i = 0; i < list.length; i++) if (list[i][0] && list[i][1] === cls && list[i][2] && seen.indexOf(list[i][2]) < 0) seen.push(list[i][2]);
    return seen;
  }
  function candidates(list) {
    var m = [];
    for (var i = 0; i < list.length; i++) if (list[i][0]) m.push(list[i][1]);
    var r = m.length ? highest(m) : null;
    pendingClauses = r == null ? [] : clausesAt(list, r);
    return r;
  }

  // "Class BASE unless X, in which case Y": a matched exception replaces the base.
  function withBase(baseLabel, gate, base, exceptions) {
    pendingClauses = [];
    if (!gate) return null;
    var m = [];
    for (var i = 0; i < exceptions.length; i++) if (exceptions[i][0]) m.push(exceptions[i][1]);
    var r = m.length ? highest(m) : base;
    pendingClauses = m.length ? clausesAt(exceptions, r) : [baseLabel];
    return r;
  }

  function out(id, section, applies, cls, why, extra) {
    var o = { rule_id: id, applies: !!applies, device_class: cls, rationale: why, source_citation: SRC + ", Section " + section, ambiguous: false, ambiguous_note: null, matched_clauses: cls == null ? [] : pendingClauses };
    pendingClauses = [];
    if (extra) for (var k in extra) o[k] = extra[k];
    return o;
  }

  var ORAL_EAR_NASAL = { oral_cavity_to_pharynx: 1, ear_canal_to_eardrum: 1, nasal_cavity: 1 };
  var HIGHER_ACTIVE = { IIa: 1, IIb: 1, III: 1 };

  var RULES = [
    function rule1(d) {
      var a = d.invasiveness === "non_invasive";
      return out("Rule 1", "4.1", a, a ? "I" : null, a ? "Non-invasive device: Class I unless a more specific rule (2-4) gives a higher class." : "Device is not non-invasive.");
    },
    function rule2(d) {
      var gate = d.invasiveness === "non_invasive" && d.channels_or_stores_for_infusion_administration_or_introduction;
      var conn = gate && !!HIGHER_ACTIVE[d.connected_to_active_device_class];
      var bag = gate && d.storage_target === "blood_bags";
      var blood = gate && (d.storage_target === "blood_or_other_body_liquids" || d.storage_target === "organs_cells_tissues") && !bag;
      var rest = gate && !(conn || bag || blood);
      var c = candidates([[conn, "IIa", "may be connected to a Class IIa, IIb or III active device"], [blood, "IIa", "channels or stores blood or other body liquids, or stores organs, cells or tissues"], [bag, "IIb", "is a blood bag"], [rest, "I", "all other cases"]]);
      return out("Rule 2", "4.2", gate, c, gate ? "Non-invasive device channelling or storing blood, body liquids, cells, tissues, liquids or gases for eventual administration into the body." : "Not a non-invasive channelling/storage device.");
    },
    function rule3(d) {
      var ni = d.invasiveness === "non_invasive";
      var mod = ni && d.modifies_biological_or_chemical_composition;
      var vitro = ni && d.in_vitro_direct_contact_with_cells_tissues_organs_or_embryos;
      var filt = d.modification_treatment_type === "filtration_centrifugation_gas_or_heat_exchange";
      var c = candidates([[mod && filt, "IIa", "the treatment consists of filtration, centrifugation or exchange of gas or heat"], [mod && !filt, "IIb", "modifies the biological or chemical composition of tissues, cells, blood or other body liquids"], [vitro, "III", "substance used in vitro in direct contact with human cells, tissues, organs or embryos"]]);
      var a = mod || vitro;
      return out("Rule 3", "4.3", a, c, a ? "Non-invasive device modifying the biological or chemical composition of tissues, cells, blood or other body liquids, or a substance used in vitro with human cells, tissues, organs or embryos." : "Does not modify biological/chemical composition.");
    },
    function rule4(d) {
      var g = d.contacts_injured_skin_or_mucous_membrane;
      var p = d.wound_contact_purpose;
      var known = p === "mechanical_barrier_compression_or_absorption" || p === "breached_dermis_secondary_intent_healing" || p === "manage_microenvironment";
      var c = candidates([
        [g && p === "mechanical_barrier_compression_or_absorption", "I", "used as a mechanical barrier, for compression or for absorption of exudates"],
        [g && p === "breached_dermis_secondary_intent_healing", "IIb", "principally for wounds that have breached the dermis and can only heal by secondary intent"],
        [g && p === "manage_microenvironment", "IIa", "principally manages the micro-environment of the wound"],
        [g && !known, "IIa", "all other cases"],
      ]);
      return out("Rule 4", "4.4", g, c, g ? "Device contacts injured skin or mucous membrane; its wound-contact purpose ('" + p + "') sets the class." : "No contact with injured skin or mucous membrane.");
    },
    function rule5(d) {
      var orifice = d.invasiveness === "invasive_body_orifice";
      var notConn = d.connected_to_active_device_class == null || d.connected_to_active_device_class === "I";
      var dg = orifice && notConn;
      var ex = !!ORAL_EAR_NASAL[d.body_orifice_site];
      var connHi = orifice && !!HIGHER_ACTIVE[d.connected_to_active_device_class];
      var absorbed = d.liable_to_be_absorbed_by_mucous_membrane;
      var c = candidates([
        [dg && d.duration === "transient", "I", "transient use"],
        [dg && d.duration === "short_term" && ex, "I", "short-term use in the oral cavity, an ear canal or the nasal cavity"],
        [dg && d.duration === "short_term" && !ex, "IIa", "short-term use"],
        [dg && d.duration === "long_term" && ex && !absorbed, "IIa", "long-term use in the oral cavity, an ear canal or the nasal cavity, and not liable to be absorbed by the mucous membrane"],
        [dg && d.duration === "long_term" && !(ex && !absorbed), "IIb", "long-term use"],
        [connHi, "IIa", "intended for connection to a Class IIa, IIb or III active device"],
      ]);
      var a = dg || connHi;
      return out("Rule 5", "5.1", a, c, a ? "Invasive via a body orifice (not surgically); duration '" + d.duration + "', site '" + d.body_orifice_site + "'." : "Not a non-surgical body-orifice device.");
    },
    function rule6(d) {
      var g = d.invasiveness === "surgically_invasive" && d.duration === "transient" && !d.is_implantable;
      var heart = d.contacts_heart_or_central_circulatory_system;
      var c = withBase("general rule for transient-use surgically invasive devices", g, "IIa", [
        [heart, "III", "intended to control, diagnose, monitor or correct a defect of the heart or central circulatory system through direct contact"],
        [d.is_reusable_surgical_instrument, "I", "is a reusable surgical instrument"],
        [heart || d.contacts_central_nervous_system, "III", "direct contact with the heart, the central circulatory system or the central nervous system"],
        [d.supplies_ionising_radiation, "IIb", "supplies energy in the form of ionising radiation"],
        [d.has_biological_effect_or_wholly_mainly_absorbed, "IIb", "has a biological effect or is wholly or mainly absorbed"],
        [d.administers_medicinal_product && d.administration_potentially_hazardous, "IIb", "administers medicinal products by a delivery system in a potentially hazardous manner"],
      ]);
      return out("Rule 6", "5.2", g, c, g ? "Surgically invasive device for transient use (under 60 minutes)." : "Not a transient-use surgically invasive device.");
    },
    function rule7(d) {
      var g = d.invasiveness === "surgically_invasive" && d.duration === "short_term" && !d.is_implantable;
      var heart = d.contacts_heart_or_central_circulatory_system;
      var c = withBase("general rule for short-term surgically invasive devices", g, "IIa", [
        [heart, "III", "intended to control, diagnose, monitor or correct a defect of the heart or central circulatory system through direct contact"],
        [heart || d.contacts_central_nervous_system, "III", "direct contact with the heart, the central circulatory system or the central nervous system"],
        [d.supplies_ionising_radiation, "IIb", "supplies energy in the form of ionising radiation"],
        [d.has_biological_effect_or_wholly_mainly_absorbed, "III", "has a biological effect or is wholly or mainly absorbed"],
        [d.undergoes_chemical_change_in_body && !d.placed_in_teeth, "IIb", "undergoes chemical change in the body (and is not placed in the teeth)"],
        [d.administers_medicinal_product, "IIb", "administers medicines"],
      ]);
      return out("Rule 7", "5.3", g, c, g ? "Surgically invasive device for short-term use (60 minutes to 30 days)." : "Not a short-term surgically invasive device.");
    },
    function rule8(d) {
      var g = d.is_implantable || (d.invasiveness === "surgically_invasive" && d.duration === "long_term");
      var joint = d.is_joint_replacement && !d.is_ancillary_component;
      var spine = d.is_spinal_disc_replacement_or_contacts_spinal_column && !d.is_ancillary_component;
      var c = withBase("general rule for implantable and long-term surgically invasive devices", g, "IIb", [
        [d.placed_in_teeth, "IIa", "placed in the teeth"],
        [d.contacts_heart_or_central_circulatory_system || d.contacts_central_nervous_system, "III", "direct contact with the heart, the central circulatory system or the central nervous system"],
        [d.has_biological_effect_or_wholly_mainly_absorbed, "III", "has a biological effect or is wholly or mainly absorbed"],
        [d.undergoes_chemical_change_in_body && !d.placed_in_teeth, "III", "undergoes chemical change in the body (and is not placed in the teeth)"],
        [d.administers_medicinal_product, "III", "administers medicinal products"],
        [d.is_active_implantable_or_accessory, "III", "is an active implantable device or its accessory"],
        [d.is_breast_implant_or_surgical_mesh, "III", "is a breast implant or surgical mesh"],
        [joint, "III", "is a total or partial joint replacement"],
        [spine, "III", "is a spinal disc replacement or an implant in contact with the spinal column"],
      ]);
      var amb = !!(g && d.is_ancillary_component && (d.is_joint_replacement || d.is_spinal_disc_replacement_or_contacts_spinal_column));
      return out("Rule 8", "5.4", g, c, g ? "Implantable device or long-term (over 30 days) surgically invasive device." : "Not implantable and not long-term surgically invasive.", {
        ambiguous: amb,
        ambiguous_note: amb ? "Ancillary component (screw, wedge, plate) of a joint or spinal implant: the rule exempts these from Class III, but MDCG 2021-24 says each must still be classified on its own intended purpose." : null,
      });
    },
    function rule9(d) {
      var eg = d.is_active && d.active_type === "therapeutic" && d.administers_or_exchanges_energy;
      var ctl = d.is_active && d.controls_monitors_or_influences_therapeutic_class_iib_device;
      var rad = d.is_active && d.emits_ionising_radiation_therapeutic;
      var aimd = d.is_active && d.controls_monitors_or_influences_active_implantable_device;
      var c = candidates([[eg, "IIa", "active therapeutic device that administers or exchanges energy"], [eg && d.energy_exchange_potentially_hazardous, "IIb", "may administer or exchange energy in a potentially hazardous way"], [ctl, "IIb", "controls, monitors or directly influences a Class IIb active therapeutic device"], [rad, "IIb", "emits ionising radiation for therapeutic purposes"], [aimd, "III", "controls, monitors or directly influences an active implantable device"]]);
      var a = eg || ctl || rad || aimd;
      return out("Rule 9", "6.1", a, c, a ? "Active therapeutic device giving or exchanging energy, or controlling a IIb therapeutic or active implantable device, or emitting therapeutic ionising radiation." : "Not an active therapeutic energy device.");
    },
    function rule10(d) {
      var dg = d.is_active && d.active_type === "diagnostic_monitoring";
      var rg = d.is_active && d.emits_ionising_radiation_diagnostic_or_interventional;
      var energy = dg && d.diagnostic_supplies_energy_absorbed_by_body;
      var light = energy && d.diagnostic_illuminates_patient_visible_spectrum_only;
      var direct = dg && d.diagnostic_allows_direct_diagnosis_or_monitoring_of_vital_physiological_processes;
      var danger = direct && d.diagnostic_variation_could_cause_immediate_danger;
      var c = candidates([
        [energy && !light, "IIa", "supplies energy that is absorbed by the human body"],
        [light, "I", "only illuminates the patient's body in the visible spectrum"],
        [dg && d.diagnostic_images_in_vivo_radiopharmaceutical_distribution, "IIa", "images the in vivo distribution of radiopharmaceuticals"],
        [direct && !danger, "IIa", "allows direct diagnosis or monitoring of vital physiological processes"],
        [danger, "IIb", "monitors vital physiological parameters whose variations could result in immediate danger to the patient"],
        [rg, "IIb", "emits ionising radiation for diagnostic or interventional radiology"],
      ]);
      var a = dg || rg;
      return out("Rule 10", "6.2", a, c, a ? "Active device for diagnosis or monitoring, and/or emitting ionising radiation for diagnostic or interventional radiology." : "Not an active diagnostic/monitoring device.");
    },
    function rule11(d) {
      if (!d.is_software) return out("Rule 11", "6.3", false, null, "Not software.");
      if (d.drives_or_influences_device_class != null) {
        var dc = d.drives_or_influences_device_class;
        var o = out("Rule 11", "6.3", true, dc, "Software that drives or influences another device takes that device's class (Class " + dc + "), per Annex VIII Chapter II, point 3.3.");
        o.source_citation = "Regulation (EU) 2017/745, Annex VIII, Chapter II, point 3.3";
        return o;
      }
      var imp = d.software_decision_impact;
      var ds = imp !== "not_applicable";
      var mon = d.software_monitors_physiological_processes;
      var vital = d.software_monitors_vital_parameters_with_immediate_danger_potential;
      var c = candidates([
        [ds && imp === "other_impact", "IIa", "provides information used to take decisions with diagnostic or therapeutic purposes"],
        [ds && imp === "serious_deterioration_or_surgical_intervention", "IIb", "those decisions may cause a serious deterioration of health or a surgical intervention"],
        [ds && imp === "death_or_irreversible_deterioration", "III", "those decisions may cause death or an irreversible deterioration of health"],
        [mon && !vital, "IIa", "monitors physiological processes"],
        [mon && vital, "IIb", "monitors vital physiological parameters whose variations could result in immediate danger to the patient"],
        [!ds && !mon, "I", "all other software"],
      ]);
      var flag = ds && (imp === "serious_deterioration_or_surgical_intervention" || imp === "death_or_irreversible_deterioration");
      return out("Rule 11", "6.3", true, c, "Software; decision-support impact '" + imp + "', monitors physiological processes: " + (mon ? "yes" : "no") + ".", {
        ambiguous: flag,
        ambiguous_note: flag ? "MDCG 2021-24 says software severity depends on context (population, ICU vs home use, the decisions informed); the same function can change class." : null,
      });
    },
    function rule12(d) {
      var g = d.is_active && d.administers_or_removes_substances_to_from_body;
      var hz = d.administration_or_removal_potentially_hazardous;
      var c = candidates([[g && !hz, "IIa", "administers or removes medicinal products, body liquids or other substances"], [g && hz, "IIb", "does so in a potentially hazardous manner"]]);
      return out("Rule 12", "6.4", g, c, g ? "Active device giving or removing medicines, body liquids or other substances." : "Does not administer or remove substances.");
    },
    function rule13(d) {
      var covered = false;
      for (var i = 8; i <= 11; i++) if (RULES[i](d).device_class != null) covered = true;
      pendingClauses = [];
      var a = d.is_active && !covered;
      return out("Rule 13", "6.5", a, a ? "I" : null, a ? "Active device not classified by Rules 9-12." : "Not active, or already classified by one of Rules 9-12.");
    },
    function rule14(d) {
      var a = d.contains_ancillary_medicinal_substance;
      return out("Rule 14", "7.1", a, a ? "III" : null, a ? "Incorporates a medicinal substance with an action ancillary to the device." : "No ancillary medicinal substance.");
    },
    function rule15(d) {
      var g = d.is_contraceptive_or_sti_prevention;
      var lt = d.is_implantable || (d.invasiveness !== "non_invasive" && d.duration === "long_term");
      var c = candidates([[g && !lt, "IIb", "used for contraception or prevention of sexually transmitted diseases"], [g && lt, "III", "is an implantable or long-term invasive device"]]);
      return out("Rule 15", "7.2", g, c, g ? "Used for contraception or to prevent transmission of STIs." : "Not a contraception/STI-prevention device.");
    },
    function rule16(d) {
      var t = d.disinfect_clean_target;
      var c = candidates([[t === "contact_lenses", "IIb", "disinfects, cleans, rinses or hydrates contact lenses"], [t === "invasive_device_end_point", "IIb", "disinfecting solution or washer-disinfector for invasive devices, as the end point of processing"], [t === "other_medical_device", "IIa", "disinfects or sterilises medical devices"]]);
      var a = c != null;
      return out("Rule 16", "7.3", a, c, a ? "Intended specifically to disinfect, clean or sterilise ('" + t + "')." : "Not a disinfecting/sterilising device (or physical cleaning only).");
    },
    function rule17(d) {
      var a = d.is_xray_diagnostic_image_recording_device;
      return out("Rule 17", "7.4", a, a ? "IIa" : null, a ? "Records diagnostic images generated by X-rays." : "Not an X-ray image recording device.");
    },
    function rule18(d) {
      var g = d.contains_human_or_animal_tissue_or_cells;
      var carve = g && d.tissue_origin === "animal" && d.tissue_contacts_intact_skin_only;
      var c = g && !carve ? "III" : carve ? "I" : null;
      return out("Rule 18", "7.5", g, c, g && !carve ? "Made using non-viable human or animal tissue or cells." : carve ? "Animal tissue touching intact skin only: outside Rule 18, Class I via Rule 1 (MDCG 2021-24 Note 3)." : "No human/animal tissue or cells.");
    },
    function rule19(d) {
      var g = d.contains_nanomaterial;
      var e = d.nanomaterial_internal_exposure_potential;
      var c = candidates([[g && (e === "high" || e === "medium"), "III", "high or medium potential for internal exposure"], [g && e === "low", "IIb", "low potential for internal exposure"], [g && e === "negligible", "IIa", "negligible potential for internal exposure"]]);
      return out("Rule 19", "7.6", g, c, g ? "Contains nanomaterial with '" + e + "' potential for internal exposure." : "No nanomaterial.");
    },
    function rule20(d) {
      var g = d.invasiveness === "invasive_body_orifice" && d.administers_medicinal_product_by_inhalation;
      var hi = d.inhalation_essential_impact_or_life_threatening;
      var c = candidates([[g && !hi, "IIa", "administers medicinal products by inhalation"], [g && hi, "IIb", "its mode of action has an essential impact on the medicinal product, or it treats life-threatening conditions"]]);
      return out("Rule 20", "7.7", g, c, g ? "Body-orifice device giving medicines by inhalation." : "Not an inhalation device.");
    },
    function rule21(d) {
      var g = d.composed_of_substances_absorbed_or_dispersed_via_orifice_or_skin;
      var sys = d.systemically_absorbed;
      var local = g && d.applied_to_skin_or_nasal_oral_cavity_to_pharynx && !sys;
      var c = candidates([[g && sys, "III", "systemically absorbed in order to achieve the intended purpose"], [g && d.achieves_purpose_in_stomach_or_lower_gi_tract && sys, "III", "achieves its purpose in the stomach or lower gastrointestinal tract and is systemically absorbed"], [local, "IIa", "applied to the skin, or in the nasal or oral cavity as far as the pharynx, and achieves its purpose there"], [g && !local && !sys, "IIb", "all other cases"]]);
      return out("Rule 21", "7.8", g, c, g ? "Substance-based device introduced via an orifice or applied to skin, absorbed or locally dispersed." : "Not a substance-based device.");
    },
    function rule22(d) {
      var a = d.is_active && d.is_active_therapeutic_with_integrated_diagnostic_function;
      return out("Rule 22", "7.9", a, a ? "III" : null, a ? "Active therapeutic device with an integrated diagnostic function that largely determines patient management (e.g. closed loop, AED)." : "No integrated diagnostic function driving therapy.");
    },
  ];

  function normalise(input) {
    var d = {};
    for (var k in DEFAULTS) d[k] = input && Object.prototype.hasOwnProperty.call(input, k) ? input[k] : DEFAULTS[k];
    return d;
  }

  function classify(input) {
    var d = normalise(input);
    var all = RULES.map(function (r) { return r(d); });
    var triggered = all.filter(function (o) { return o.applies && o.device_class != null; });
    var cls = highest(triggered.map(function (o) { return o.device_class; }));
    var q = [];
    if (cls === "I") {
      if (d.placed_on_market_sterile) q.push("Is");
      if (d.has_measuring_function) q.push("Im");
      if (d.is_reusable_surgical_instrument) q.push("Ir");
    }
    return { device_class: cls, qualifiers: q, triggered_rules: triggered, all_rule_outcomes: all, device: d };
  }

  // --- standards mapping (Annex I GSPR categories) -------------------------
  function std(id, title, note) { return { standard_id: id, title: title, note: note || "" }; }

  function bioContact(d) {
    return d.invasiveness !== "non_invasive" || d.is_implantable || d.contacts_injured_skin_or_mucous_membrane ||
      d.contacts_heart_or_central_circulatory_system || d.contacts_central_nervous_system ||
      d.in_vitro_direct_contact_with_cells_tissues_organs_or_embryos || d.tissue_contacts_intact_skin_only ||
      d.placed_in_teeth || d.is_spinal_disc_replacement_or_contacts_spinal_column || d.is_joint_replacement ||
      d.is_breast_implant_or_surgical_mesh;
  }

  var GSPR = [
    ["risk_management", "Risk management system", "Annex I, Section 3", function () { return true; }, function () { return [std("ISO 14971", "Application of risk management to medical devices")]; }],
    ["quality_management_system", "Quality management system", "Article 10(9)", function () { return true; }, function () { return [std("ISO 13485", "Quality management systems - Requirements for regulatory purposes")]; }],
    ["clinical_evaluation", "Clinical evaluation", "Article 61(1), Annex XIV", function () { return true; }, function () { return [std("ISO 14155", "Clinical investigation of medical devices for human subjects - Good clinical practice", "Only if the route involves a clinical investigation.")]; }],
    ["labeling_and_ifu", "Label and instructions for use", "Annex I, Section 23", function () { return true; }, function () { return [std("ISO 15223-1", "Symbols to be used with information supplied by the manufacturer"), std("ISO 20417", "Information to be supplied by the manufacturer")]; }],
    ["biocompatibility", "Biological safety / biocompatibility", "Annex I, Sections 10.1(b), 10.2", bioContact, function () { return [std("ISO 10993-1", "Biological evaluation - Evaluation and testing within a risk management process", "Framework standard; further parts depend on contact type and duration.")]; }],
    ["infection_and_sterility", "Sterility and microbial contamination", "Annex I, Section 11", function (d) { return d.placed_on_market_sterile; }, function () { return [std("ISO 11135", "Sterilization - Ethylene oxide", "Method-dependent."), std("ISO 11137", "Sterilization - Radiation", "Method-dependent."), std("ISO 17665", "Sterilization - Moist heat", "Method-dependent."), std("ISO 11607", "Packaging for terminally sterilized medical devices")]; }],
    ["biological_origin_materials", "Materials of biological origin", "Annex I, Section 13", function (d) { return d.contains_human_or_animal_tissue_or_cells; }, function (d) {
      if (d.tissue_origin === "animal") return [std("ISO 22442", "Medical devices utilizing animal tissues and their derivatives")];
      if (d.tissue_origin === "human") return [std("Directive 2004/23/EC", "EU tissues and cells directive", "A directive, not an ISO/IEC standard.")];
      return [];
    }],
    ["incorporated_medicinal_substances", "Incorporated medicinal substances", "Annex I, Section 12", function (d) { return d.administers_medicinal_product || d.contains_ancillary_medicinal_substance || d.composed_of_substances_absorbed_or_dispersed_via_orifice_or_skin; }, function () { return []; }],
    ["software_lifecycle", "Software lifecycle and security", "Annex I, Section 17", function (d) { return d.is_software; }, function () { return [std("IEC 62304", "Medical device software - Software life cycle processes"), std("IEC 82304-1", "Health software - General requirements for product safety", "Standalone software products."), std("IEC 81001-5-1", "Health software - Security activities in the product life cycle")]; }],
    ["electrical_mechanical_safety_emc", "Electrical, mechanical and EMC safety", "Annex I, Sections 14, 18, 20", function (d) { return d.is_active; }, function () { return [std("IEC 60601-1", "Medical electrical equipment - General requirements for basic safety and essential performance"), std("IEC 60601-1-2", "Medical electrical equipment - Electromagnetic disturbances")]; }],
    ["radiation_protection", "Protection against radiation", "Annex I, Section 16", function (d) { return d.supplies_ionising_radiation || d.emits_ionising_radiation_therapeutic || d.emits_ionising_radiation_diagnostic_or_interventional || d.is_xray_diagnostic_image_recording_device; }, function () { return [std("IEC 60601-1-3", "Radiation protection in diagnostic X-ray equipment", "Modality-specific parts also apply.")]; }],
    ["active_implantable_devices", "Active implantable devices", "Annex I, Section 19", function (d) { return d.is_active_implantable_or_accessory || (d.is_active && d.is_implantable); }, function () { return [std("ISO 14708-1", "Active implantable medical devices - General requirements")]; }],
    ["measuring_function", "Measuring function", "Annex I, Section 15", function (d) { return d.has_measuring_function; }, function () { return []; }],
    ["energy_or_substance_delivery", "Energy or substance delivery", "Annex I, Section 21", function (d) { return d.administers_or_exchanges_energy || d.administers_or_removes_substances_to_from_body || d.channels_or_stores_for_infusion_administration_or_introduction; }, function () { return []; }],
  ];

  function mapStandards(input) {
    var d = normalise(input);
    return GSPR.map(function (g) {
      var applies = !!g[3](d);
      return { requirement_id: g[0], title: g[1], source_citation: g[2], applies: applies, standards: applies ? g[4](d) : [] };
    });
  }

  // --- regulatory pathway (port of regulatory_pathway/eu_mdr.py) -----------
  var REG = "Regulation (EU) 2017/745";
  function buildPathway(input) {
    var d = normalise(input), r = classify(d), cls = r.device_class, q = r.qualifiers;
    if (cls == null) return [];
    var implantable = d.is_implantable, items = [];
    function add(id, title, applies, summary, citation, caveat) {
      items.push({ item_id: id, title: title, applies: !!applies, summary: summary, citation: citation, caveat: caveat || "" });
    }
    var route, nb, exemptType = d.is_ancillary_component || d.placed_in_teeth;
    if (cls === "I" && !q.length) {
      route = "Self-declaration. The manufacturer draws up the technical documentation (Annexes II and III) and issues an EU declaration of conformity. No notified body is involved.";
      nb = "None";
    } else if (cls === "I") {
      var aspects = {
        Is: "establishing, securing and maintaining sterile conditions",
        Im: "conformity with the metrological requirements",
        Ir: "the reuse of the device (cleaning, disinfection, sterilisation, maintenance, functional testing and instructions)",
      };
      route = "Self-declaration for the device itself, plus a notified body under Annex IX Chapters I and III or Annex XI Part A, limited to: " + q.map(function (x) { return aspects[x]; }).join("; ") + ".";
      nb = "Limited to the sterile / measuring / reusable-instrument aspects";
    } else if (cls === "IIa") {
      route = "Quality management system assessment under Annex IX Chapters I and III, with technical documentation assessed for at least one representative device per device category. Alternative: technical documentation (Annexes II and III) with production verification under Annex XI Section 10 or 18.";
      nb = "Required";
    } else if (cls === "IIb") {
      route = "Quality management system assessment under Annex IX Chapters I and III, with technical documentation assessed " +
        (implantable && !exemptType ? "for every device, because it is a Class IIb implantable device. " : "for at least one representative device per generic device group. ") +
        "Alternative: EU type-examination (Annex X) with product conformity verification (Annex XI).";
      nb = "Required";
    } else {
      route = "Full quality management system and technical documentation assessment under Annex IX, including assessment of the technical documentation of every device (Chapter II). Alternative: EU type-examination (Annex X) with product conformity verification (Annex XI).";
      nb = "Required, including review of the design of each device";
    }
    add("conformity_route", "Conformity assessment route", true, route, REG + ", Article 52",
      cls === "IIb" && implantable && exemptType ? "Article 52(4) exempts sutures, staples, dental fillings, dental braces, tooth crowns, screws, wedges, plates, wires, pins, clips and connectors from per-device assessment; check whether this device is one of them." : "");
    add("notified_body", "Notified body involvement", true, nb, REG + ", Article 52");

    var inv = implantable || cls === "III";
    add("clinical_investigation", "Clinical investigation expected", inv,
      inv ? "For implantable and Class III devices, clinical investigations are expected unless an exemption applies (for example demonstrated equivalence to the manufacturer's own marketed device, or one of the listed well-established device types)." : "Clinical evaluation is still required, but it can rest on existing clinical data where sufficient.",
      inv ? REG + ", Article 61(4)-(6)" : REG + ", Article 61 and Annex XIV");
    var consult = (cls === "III" && implantable) || (cls === "IIb" && d.is_active && d.administers_or_removes_substances_to_from_body);
    add("clinical_evaluation_consultation", "Expert panel consultation on the clinical evaluation", consult,
      consult ? "The notified body's clinical evaluation assessment report goes to an expert panel before certification (Class III implantable devices, and Class IIb active devices that administer or remove a medicinal product)." : "Not triggered by this class and device type.",
      REG + ", Article 54",
      consult && cls === "IIb" ? "For Class IIb this applies only if the substance administered or removed is a medicinal product." : "");
    var sscp = implantable || cls === "III";
    add("sscp", "Summary of safety and clinical performance", sscp,
      sscp ? "A public summary written for the intended user (and patient where relevant), validated by the notified body and published in EUDAMED." : "Only required for implantable and Class III devices.",
      REG + ", Article 32");
    add("implant_card", "Implant card and patient information", implantable,
      implantable ? "The manufacturer supplies an implant card and information for the patient with the device." : "Only required for implantable devices.",
      REG + ", Article 18",
      implantable ? "Sutures, staples, dental fillings, dental braces, tooth crowns, screws, wedges, plates, wires, pins, clips and connectors are exempt." : "");

    var pms, pmsCite;
    if (cls === "I") { pms = "A post-market surveillance report, updated when necessary and available to the competent authority on request."; pmsCite = REG + ", Article 85"; }
    else if (cls === "IIa") { pms = "A periodic safety update report (PSUR), updated when necessary and at least every two years."; pmsCite = REG + ", Article 86"; }
    else { pms = "A periodic safety update report (PSUR), updated at least annually" + (cls === "III" || implantable ? ", and submitted to the notified body through EUDAMED." : "."); pmsCite = REG + ", Article 86"; }
    add("post_market_reporting", "Post-market surveillance reporting", true, pms, pmsCite);

    var med = d.contains_ancillary_medicinal_substance;
    add("medicinal_substance_consultation", "Medicines authority opinion on the incorporated substance", med,
      med ? "The notified body must seek a scientific opinion from a medicines competent authority or the EMA on the quality and safety of the substance, including its benefit and risk in the device." : "Only for devices incorporating an ancillary medicinal substance.",
      REG + ", Annex IX Section 5.2");
    var tissue = d.contains_human_or_animal_tissue_or_cells && !(d.tissue_origin === "animal" && d.tissue_contacts_intact_skin_only);
    var human = d.tissue_origin === "human";
    add("tissue_consultation", "Consultation on tissues or cells of human or animal origin", tissue,
      tissue ? (human ? "The notified body must seek an opinion from a human tissues and cells competent authority on donation, procurement and testing." : "For animal tissues the notified body applies the particular requirements of Regulation (EU) No 722/2012 (TSE risk), where relevant.") : "Only for devices made with non-viable human or animal tissues or cells.",
      tissue ? REG + (human ? ", Annex IX Section 5.3.1" : ", Annex IX Section 5.3.2") : REG + ", Annex IX Section 5.3");
    var subst = d.composed_of_substances_absorbed_or_dispersed_via_orifice_or_skin && d.systemically_absorbed;
    add("substance_consultation", "Medicines authority opinion on absorbed substances", subst,
      subst ? "For substance-based devices that are systemically absorbed, the notified body seeks a scientific opinion from a medicines competent authority on compliance with the relevant medicinal-product requirements." : "Only for substance-based devices that are systemically absorbed.",
      REG + ", Annex IX Section 5.4");
    add("general_obligations", "Obligations for every class", true,
      "Technical documentation (Annexes II and III), EU declaration of conformity (Article 19) and CE marking (Article 20); UDI assignment (Article 27); registration of the device and manufacturer in EUDAMED (Articles 29 and 31); a person responsible for regulatory compliance (Article 15); a post-market surveillance system and vigilance reporting (Articles 83 and 87).",
      REG + ", Articles 10, 15, 19, 20, 27, 29, 31, 83, 87");
    return items;
  }

  // --- class drivers (port of rules_engine/sensitivity.py) ------------------
  function classDrivers(input) {
    var d = normalise(input), base = classify(d).device_class, drivers = [];
    for (var k in DEFAULTS) {
      if (k === "name" || d[k] === DEFAULTS[k]) continue;
      var v = {}; for (var j in d) v[j] = d[j];
      v[k] = DEFAULTS[k];
      var other = classify(v).device_class;
      if (other !== base) drivers.push({ attribute: k, value: d[k], class_without: other });
    }
    return drivers;
  }

  var api = { classify: classify, mapStandards: mapStandards, buildPathway: buildPathway, classDrivers: classDrivers, DEFAULTS: DEFAULTS, RANK: RANK };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.MDREngine = api;
})(typeof window !== "undefined" ? window : this);
