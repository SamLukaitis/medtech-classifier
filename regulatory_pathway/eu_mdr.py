"""What a classification means in practice under Regulation (EU) 2017/745.

Given a device and its class, lists the conformity assessment route and
the main obligations that follow from the class and a few device
attributes: notified body involvement, clinical evidence expectations,
the summary of safety and clinical performance, implant card,
post-market reporting, and the consultations some special devices need.

Like the rules engine this is deterministic: each item is a fixed
condition on the class and attributes, with the Article or Annex it
comes from. Unlike ``rules_engine`` (written against verbatim text saved
in docs/legal_sources/), the citations here are article-level pointers
and the summaries are paraphrases, so read the cited provision before
relying on any item. Custom-made and investigational devices, and
transitional arrangements under Article 120, are not modelled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rules_engine.models import ClassificationResult, DeviceAttributes, DeviceClass, TissueOrigin

_REG = "Regulation (EU) 2017/745"


@dataclass
class PathwayItem:
    item_id: str
    title: str
    applies: bool
    summary: str
    citation: str
    caveat: str = ""


def build_pathway(device: DeviceAttributes, classification: ClassificationResult) -> list[PathwayItem]:
    cls: Optional[DeviceClass] = classification.device_class
    if cls is None:
        return []
    qualifiers = [q.value for q in classification.qualifiers]
    implantable = device.is_implantable
    items: list[PathwayItem] = []

    # --- conformity assessment route (Article 52) ---
    if cls == DeviceClass.I and not qualifiers:
        route = (
            "Self-declaration. The manufacturer draws up the technical documentation (Annexes II and III) "
            "and issues an EU declaration of conformity. No notified body is involved."
        )
        nb = "None"
    elif cls == DeviceClass.I:
        aspects = {
            "Is": "establishing, securing and maintaining sterile conditions",
            "Im": "conformity with the metrological requirements",
            "Ir": "the reuse of the device (cleaning, disinfection, sterilisation, maintenance, functional testing and instructions)",
        }
        route = (
            "Self-declaration for the device itself, plus a notified body under Annex IX Chapters I and III "
            "or Annex XI Part A, limited to: " + "; ".join(aspects[q] for q in qualifiers) + "."
        )
        nb = "Limited to the sterile / measuring / reusable-instrument aspects"
    elif cls == DeviceClass.IIA:
        route = (
            "Quality management system assessment under Annex IX Chapters I and III, with technical "
            "documentation assessed for at least one representative device per device category. Alternative: "
            "technical documentation (Annexes II and III) with production verification under Annex XI Section 10 or 18."
        )
        nb = "Required"
    elif cls == DeviceClass.IIB:
        every = implantable and not (device.is_ancillary_component or device.placed_in_teeth)
        route = (
            "Quality management system assessment under Annex IX Chapters I and III, with technical documentation assessed "
            + (
                "for every device, because it is a Class IIb implantable device. "
                if every
                else "for at least one representative device per generic device group. "
            )
            + "Alternative: EU type-examination (Annex X) with product conformity verification (Annex XI)."
        )
        nb = "Required"
    else:
        route = (
            "Full quality management system and technical documentation assessment under Annex IX, including "
            "assessment of the technical documentation of every device (Chapter II). Alternative: EU "
            "type-examination (Annex X) with product conformity verification (Annex XI)."
        )
        nb = "Required, including review of the design of each device"

    route_caveat = ""
    if cls == DeviceClass.IIB and implantable and (device.is_ancillary_component or device.placed_in_teeth):
        route_caveat = (
            "Article 52(4) exempts sutures, staples, dental fillings, dental braces, tooth crowns, screws, wedges, "
            "plates, wires, pins, clips and connectors from per-device assessment; check whether this device is one of them."
        )
    items.append(PathwayItem("conformity_route", "Conformity assessment route", True, route, f"{_REG}, Article 52", route_caveat))
    items.append(PathwayItem("notified_body", "Notified body involvement", True, nb, f"{_REG}, Article 52"))

    # --- clinical evidence ---
    investigation = implantable or cls == DeviceClass.III
    items.append(
        PathwayItem(
            "clinical_investigation",
            "Clinical investigation expected",
            investigation,
            (
                "For implantable and Class III devices, clinical investigations are expected unless an exemption "
                "applies (for example demonstrated equivalence to the manufacturer's own marketed device, or one of "
                "the listed well-established device types)."
                if investigation
                else "Clinical evaluation is still required, but it can rest on existing clinical data where sufficient."
            ),
            f"{_REG}, Article 61(4)-(6)" if investigation else f"{_REG}, Article 61 and Annex XIV",
        )
    )
    consult = (cls == DeviceClass.III and implantable) or (
        cls == DeviceClass.IIB and device.is_active and device.administers_or_removes_substances_to_from_body
    )
    items.append(
        PathwayItem(
            "clinical_evaluation_consultation",
            "Expert panel consultation on the clinical evaluation",
            consult,
            (
                "The notified body's clinical evaluation assessment report goes to an expert panel before "
                "certification (Class III implantable devices, and Class IIb active devices that administer or "
                "remove a medicinal product)."
                if consult
                else "Not triggered by this class and device type."
            ),
            f"{_REG}, Article 54",
            (
                "For Class IIb this applies only if the substance administered or removed is a medicinal product."
                if consult and cls == DeviceClass.IIB
                else ""
            ),
        )
    )
    sscp = implantable or cls == DeviceClass.III
    items.append(
        PathwayItem(
            "sscp",
            "Summary of safety and clinical performance",
            sscp,
            (
                "A public summary written for the intended user (and patient where relevant), validated by the "
                "notified body and published in EUDAMED."
                if sscp
                else "Only required for implantable and Class III devices."
            ),
            f"{_REG}, Article 32",
        )
    )
    items.append(
        PathwayItem(
            "implant_card",
            "Implant card and patient information",
            implantable,
            (
                "The manufacturer supplies an implant card and information for the patient with the device."
                if implantable
                else "Only required for implantable devices."
            ),
            f"{_REG}, Article 18",
            (
                "Sutures, staples, dental fillings, dental braces, tooth crowns, screws, wedges, plates, wires, pins, "
                "clips and connectors are exempt."
                if implantable
                else ""
            ),
        )
    )

    # --- post-market ---
    if cls == DeviceClass.I:
        pms = "A post-market surveillance report, updated when necessary and available to the competent authority on request."
        pms_cite = f"{_REG}, Article 85"
    elif cls == DeviceClass.IIA:
        pms = "A periodic safety update report (PSUR), updated when necessary and at least every two years."
        pms_cite = f"{_REG}, Article 86"
    else:
        pms = "A periodic safety update report (PSUR), updated at least annually" + (
            ", and submitted to the notified body through EUDAMED." if cls == DeviceClass.III or implantable else "."
        )
        pms_cite = f"{_REG}, Article 86"
    items.append(PathwayItem("post_market_reporting", "Post-market surveillance reporting", True, pms, pms_cite))

    # --- special consultations during conformity assessment ---
    medicinal = device.contains_ancillary_medicinal_substance
    items.append(
        PathwayItem(
            "medicinal_substance_consultation",
            "Medicines authority opinion on the incorporated substance",
            medicinal,
            (
                "The notified body must seek a scientific opinion from a medicines competent authority or the EMA "
                "on the quality and safety of the substance, including its benefit and risk in the device."
                if medicinal
                else "Only for devices incorporating an ancillary medicinal substance."
            ),
            f"{_REG}, Annex IX Section 5.2",
        )
    )
    tissue = device.contains_human_or_animal_tissue_or_cells and not (
        device.tissue_origin == TissueOrigin.ANIMAL and device.tissue_contacts_intact_skin_only
    )
    if device.tissue_origin == TissueOrigin.HUMAN:
        tissue_text = "The notified body must seek an opinion from a human tissues and cells competent authority on donation, procurement and testing."
        tissue_cite = f"{_REG}, Annex IX Section 5.3.1"
    else:
        tissue_text = "For animal tissues the notified body applies the particular requirements of Regulation (EU) No 722/2012 (TSE risk), where relevant."
        tissue_cite = f"{_REG}, Annex IX Section 5.3.2"
    items.append(
        PathwayItem(
            "tissue_consultation",
            "Consultation on tissues or cells of human or animal origin",
            tissue,
            tissue_text if tissue else "Only for devices made with non-viable human or animal tissues or cells.",
            tissue_cite if tissue else f"{_REG}, Annex IX Section 5.3",
        )
    )
    substance = device.composed_of_substances_absorbed_or_dispersed_via_orifice_or_skin and device.systemically_absorbed
    items.append(
        PathwayItem(
            "substance_consultation",
            "Medicines authority opinion on absorbed substances",
            substance,
            (
                "For substance-based devices that are systemically absorbed, the notified body seeks a scientific "
                "opinion from a medicines competent authority on compliance with the relevant medicinal-product requirements."
                if substance
                else "Only for substance-based devices that are systemically absorbed."
            ),
            f"{_REG}, Annex IX Section 5.4",
        )
    )

    # --- applies to every device ---
    items.append(
        PathwayItem(
            "general_obligations",
            "Obligations for every class",
            True,
            "Technical documentation (Annexes II and III), EU declaration of conformity (Article 19) and CE marking "
            "(Article 20); UDI assignment (Article 27); registration of the device and manufacturer in EUDAMED "
            "(Articles 29 and 31); a person responsible for regulatory compliance (Article 15); a post-market "
            "surveillance system and vigilance reporting (Articles 83 and 87).",
            f"{_REG}, Articles 10, 15, 19, 20, 27, 29, 31, 83, 87",
        )
    )
    return items
