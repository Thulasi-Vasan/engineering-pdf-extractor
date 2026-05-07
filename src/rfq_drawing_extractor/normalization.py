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
    normalized = normalize_engineering_symbol_artifacts(normalized)
    normalized = _collapse_overprinted_words(normalized)

    cleaned_lines = []
    for line in normalized.splitlines():
        line = re.sub(r"[ \t]+", " ", line).strip()
        if line:
            cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def normalize_reconstructed_text(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    normalized = normalize_text(text)
    deduped = _collapse_overprinted_words(normalized)
    if deduped != normalized:
        warnings.append("Collapsed repeated/overprinted character runs.")
        normalized = deduped
    return normalized, warnings


def normalize_engineering_symbol_artifacts(text: str) -> str:
    normalized = text
    normalized = _normalize_tolerance_symbol_artifacts(normalized)
    normalized = _normalize_diameter_artifacts(normalized)
    return normalized


def _normalize_tolerance_symbol_artifacts(text: str) -> str:
    normalized = text
    normalized = re.sub(r"`\s*(?=\d|\.)", "±", normalized)
    normalized = re.sub(r"(?<=\d)\s*~", "°", normalized)
    normalized = re.sub(r"(?<=/\d)\s*~", "°", normalized)
    return normalized


def _normalize_diameter_artifacts(text: str) -> str:
    normalized = text
    normalized = re.sub(r"\bn(?=\d+(?:\.\d+)?)", "Ø", normalized)
    normalized = re.sub(r"\bn(?=\.\d+)", "Ø", normalized)
    return normalized


def _collapse_overprinted_words(text: str) -> str:
    return re.sub(r"\b[A-Za-z]{4,}\b", lambda match: _collapse_repeated_word(match.group(0)), text)


def _collapse_repeated_word(word: str) -> str:
    runs = re.findall(r"([A-Za-z])\1*", word)
    if len(runs) < 3:
        if len(runs) >= 2 and all(len(match.group(0)) >= 2 for match in re.finditer(r"([A-Za-z])\1*", word)):
            return "".join(runs)
        return word
    run_lengths = [len(match.group(0)) for match in re.finditer(r"([A-Za-z])\1*", word)]
    if not run_lengths:
        return word
    repeated_runs = sum(1 for length in run_lengths if length >= 2)
    if repeated_runs / len(run_lengths) < 0.6:
        return word
    collapsed = "".join(runs)
    if len(collapsed) < 3:
        return word
    return collapsed


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
