import csv
import itertools
from typing import Callable, List, Dict, Any


FIELD_MAP = {
    # 0: [{"label": "HH"}],
    # 1: [{"label": "Circ Pump Status"}, {"label": "AutoCirc"}, {"label": "Man Circ"}],
    # 2: [{"label": "Pump Status A"}, {"label": "Pump Status B"}],
    # 4: [{"label": "CR?"}],
    # 5: [{"label": "Curr. Temp"}],
    # 7: [{"label": "MONTH"}, {"label": "DAY"}],
    # 8: [{"label": "Setpoint"}],
    # 10: [{"label": "Heater?"}],
    # 11: [{"label": "MM"}],
    # 13: [{"label": "CR Replace?"}],
}

KNOWN_FIELDS = {
    "days": {
        "values": [19]  # We expect this pattern in the decoded data
    },
}


def load_packets(csv_path):
    with open(csv_path, newline='') as f:
        return [list(map(int, row)) for row in csv.reader(f)]


def extract_claimed_indices(field_map):
    return set(field_map.keys())


def generate_dynamic_transforms() -> Dict[str, Callable[[int], Any]]:
    transforms = {"b": lambda b: b}

    for shift in range(1, 5):
        transforms[f"b >> {shift}"] = lambda b, s=shift: b >> s
        transforms[f"b << {shift}"] = lambda b, s=shift: (b << s) & 0xFF

    for mask in [0x01, 0x02, 0x04, 0x08, 0x0F, 0xF0, 0x3F, 0xC0]:
        transforms[f"b & 0x{mask:02X}"] = lambda b, m=mask: b & m

    for xor in [0x01, 0xFF, 0x55, 0xAA]:
        transforms[f"b ^ 0x{xor:02X}"] = lambda b, x=xor: b ^ x

    for div in [2, 5, 10, 16, 32, 64, 100]:
        transforms[f"b / {div}"] = lambda b, d=div: round(b / d, 3)

    transforms["(b & 0xF0) >> 4"] = lambda b: (b & 0xF0) >> 4
    transforms["(b & 0x0F) << 4"] = lambda b: (b & 0x0F) << 4

    return transforms


def analyze_field(packet_series: List[int], transform_fn: Callable[[int], Any]):
    values = [transform_fn(b) for b in packet_series]
    transitions = sum(1 for a, b in zip(values, values[1:]) if a != b)
    return {
        "values": values,
        "unique_count": len(set(values)),
        "transitions": transitions,
        "min": min(values),
        "max": max(values),
        "fingerprint": values[:10],
    }


def match_known_sequence(series: List[Any], pattern: List[Any]) -> bool:
    """Check if `pattern` appears as a subsequence in `series`."""
    if len(series) < len(pattern):
        return False
    for i in range(len(series) - len(pattern) + 1):
        if series[i:i + len(pattern)] == pattern:
            return True
    return False


def match_known_values_set(series: List[Any], expected_values: List[Any]) -> bool:
    return set(series).issuperset(set(expected_values))


def discover_candidate_fields(packets, field_map, known_fields):
    claimed_indices = extract_claimed_indices(field_map)
    field_len = len(packets[0])
    results = []
    transforms = generate_dynamic_transforms()

    for byte_index in range(field_len):
        if byte_index in claimed_indices:
            continue

        raw_series = [packet[byte_index] for packet in packets]

        for tname, tfunc in transforms.items():
            try:
                analysis = analyze_field(raw_series, tfunc)
                values = analysis["values"]

                match_info = None
                for label, criteria in known_fields.items():
                    if "values" in criteria:
                        if isinstance(criteria["values"], list):
                            if all(isinstance(v, (int, float)) for v in criteria["values"]):
                                if len(criteria["values"]) > 3:
                                    matched = match_known_sequence(values, criteria["values"])
                                else:
                                    matched = match_known_values_set(values, criteria["values"])

                                if matched:
                                    match_info = label
                                    break

                if analysis["unique_count"] <= 1 and not match_info:
                    continue

                results.append({
                    "byte": byte_index,
                    "transform": tname,
                    "unique_vals": analysis["unique_count"],
                    "transitions": analysis["transitions"],
                    "range": f"{analysis['min']}–{analysis['max']}",
                    "preview": analysis["fingerprint"],
                    "match": match_info,
                })

            except Exception:
                continue

    return sorted(results, key=lambda r: (-r['transitions'], -r['unique_vals']))


def print_markdown_table(candidates):
    print("### 🧪 Candidate Byte Fields (Dynamic Transforms)\n")
    print("| Byte | Transform        | Unique | Transitions | Range     | Preview            | Match              |")
    print("|------|------------------|--------|-------------|-----------|---------------------|--------------------|")
    for c in candidates:
        preview_str = "[" + ", ".join(str(v) for v in c["preview"]) + "]"
        match_str = c["match"] or ""
        print(f"| {c['byte']:>4} | {c['transform']:<16} | {c['unique_vals']:>6} | {c['transitions']:>11} | {c['range']:<9} | {preview_str:<19} | {match_str:<18} |")


def main():
    csv_path = "1747660197.24942-debug_messages.csv"
    packets = load_packets(csv_path)
    print(packets)
    candidates = discover_candidate_fields(packets, FIELD_MAP, KNOWN_FIELDS)
    print_markdown_table(candidates)


if __name__ == "__main__":
    main()
