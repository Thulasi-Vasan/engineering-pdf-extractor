from __future__ import annotations

import re


CID_MAP = {
    "(cid:19)": "0",
    "(cid:20)": "1",
    "(cid:21)": "2",
    "(cid:22)": "3",
    "(cid:23)": "4",
    "(cid:24)": "5",
    "(cid:25)": "6",
    "(cid:26)": "7",
    "(cid:27)": "8",
    "(cid:28)": "9",
    "(cid:38)": "C",
    "(cid:131)": "°",
}


def normalize_text(text: str) -> str:
    if not text:
        return ""

    normalized = text
    for raw, replacement in CID_MAP.items():
        normalized = normalized.replace(raw, replacement)

    normalized = normalized.replace("⌀", "Ø")
    normalized = normalized.replace("ø", "Ø")
    normalized = normalized.replace("“", '"').replace("”", '"')
    normalized = normalized.replace("′", "'").replace("″", '"')
    normalized = normalized.replace("–", "-").replace("—", "-")
    normalized = normalized.replace("UNlT", "UNIT")
    normalized = _restore_common_pdf_spacing(normalized)
    normalized = _restore_common_fraction_sizes(normalized)

    cleaned_lines = []
    for line in normalized.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def text_preview(text: str, *, limit: int = 240) -> str:
    compact = " ".join(normalize_text(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _restore_common_fraction_sizes(text: str) -> str:
    restored = text
    replacements = {
        '14"': '1/4"',
        '38"': '3/8"',
        '58"': '5/8"',
        '112"': '1 1/2"',
    }
    for raw, replacement in replacements.items():
        restored = re.sub(rf"(?<![\d/]){re.escape(raw)}", replacement, restored)
    return restored


def _restore_common_pdf_spacing(text: str) -> str:
    restored = text
    replacements = {
        "Anglevalve": "Angle valve",
        "Dischargeflange": "Discharge flange",
        "Solenoidvalve": "Solenoid valve",
        "Suctionflange": "Suction flange",
        "Cablebox": "Cable box",
        "Serviceflange": "Service flange",
        "Oildrainvalve": "Oil drain valve",
        "Oillevelswitch": "Oil level switch",
        "Oilsightglass": "Oil sight glass",
        "Oilheater": "Oil heater",
        "Oilfiltercartridge": "Oil filter cartridge",
        "Oilpressure": "Oil pressure",
        "differentialswitch": "differential switch",
        "Oilconnector": "Oil connector",
        "Overflowport": "Over flow port",
        "Dischargetemp.sensor": "Discharge temp. sensor",
        "Economizerconnector": "Economizer connector",
        "SafetyValve": "Safety Valve",
        "Liquidinjection": "Liquid injection",
        "injectionconnector": "injection connector",
        "servicevalve": "service valve",
        "MicroControlSystems": "Micro Control Systems",
        "DimensionalOutlineDrawing": "Dimensional Outline Drawing",
        "ComponentDescription": "Component Description",
        "Compressoroutline": "Compressor outline",
        "HanbellModel": "Hanbell Model",
        "DrawnBy": "Drawn By",
        "SI:mmImperial": "SI: mm Imperial",
        "RC2-100140": "RC2-100/140",
        "150W300W": "150W/300W",
        "Stepless(NCorNO)": "Stepless(NC or NO)",
    }
    for raw, replacement in replacements.items():
        restored = restored.replace(raw, replacement)
    return restored
