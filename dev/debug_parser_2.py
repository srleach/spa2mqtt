import csv

FIELD_MAP = {
    0: [
        {
            "name": "TIME: Hours",
            "transform": lambda b: b ^ 6,
            "label": "HH",
            "note": "XOR 6"
        },
    ],
    1: [
        {
            "name": "Circulation Pump State",
            "transform": lambda b: b >> 6 & 1,
            "label": "Circ Pump Status",
            "note": "SHIFT 6 MASK 1"
        },
        {
            "name": "Auto Circ",
            "transform": lambda b: b >> 6 & 1,
            "label": "AutoCirc",
            "note": "SHIFT 6 MASK 1 (Same as Circ Pump State?)"
        },
        {
            "name": "Man Circ",
            "transform": lambda b: b >> 7 & 1,
            "label": "Man Circ",
            "note": "SHIFT 7 MASK 1"
        },
    ],
    2: [
        {
            "name": "Pump State A",
            "transform": lambda b: b >> 4 & 1,
            "label": "Pump Status A",
            "note": "SHIFT 4 MASK 1"
        },
        {
            "name": "Pump State B",
            "transform": lambda b: b >> 2 & 1,
            "label": "Pump Status B",
            "note": "SHIFT 2 MASK 1"
        },
    ],
    3: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
    4: [
        {
            "name": "UNKNOWN (Maybe Clearray Active?)",
            "transform": lambda b: (b ^ 6) & 1,
            "label": "CR?",
            "note": "SHIFT 6 MASK 1"
        },

    ],
    5: [
        {
            "name": "Temperature",
            "transform": lambda b: (b ^ 2) / 2,
            "label": "Curr. Temp",
            "note": "XOR 0x1"
        },
    ],
    6: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
    7: [
        {
            "name": "Date: Month",
            "transform": lambda b: b & 7,
            "label": "MONTH",
            "note": "SHIFT 7"
        },
        {
            "name": "Date: Day",
            "transform": lambda b: b >> 3,
            "label": "DAY",
            "note": "SHIFT 3"
        },
    ],
    8: [
        {
            "name": "Setpoint",
            "transform": lambda b: b / 2,
            "label": "Setpoint",
            "note": "IDENTITY / 2"
        },
    ],
    9: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
    10: [
        {
            "name": "Heater State",
            "transform": lambda b: b >> 6 & 1,
            "label": "Heater?",
            "note": "SHIFT 6 MASK 1"
        },

    ],
    11: [
        {
            "name": "TIME: Minutes",
            "transform": lambda b: b,
            "label": "MM",
            "note": "IDENTITY"
        },
    ],
    12: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
    13: [
        {
            "name": "Clearray Life",
            "transform": lambda b: b,
            "label": "CR Replace?",
            "note": "IDENTITY"
        },

    ],
    14: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
    15: [
        {
            "name": "",
            "transform": lambda b: None,
            "label": "",
            "note": ""
        },
    ],
}

KNOWN_FIELDS = {
    "filter_life": {
        "values": [120, 130, 140, 160]
    },
}

def load_csv(path):
    with open(path, newline='') as f:
        return [list(map(int, row)) for row in csv.reader(f)]

def extract_claimed_fields(field_map):
    claimed_fields = set()
    for byte_index, fields in field_map.items():
        for field in fields:
            claimed_fields.add((byte_index, field["label"]))
    return claimed_fields

def apply_bitwise_candidates(byte):
    return {
        "identity": byte,
        "xor_1": byte ^ 0x01,
        "xor_2": byte ^ 0x02,
        "xor_6": byte ^ 0x06,
        "div2": byte / 2,
        "xor2_div2": (byte ^ 0x02) / 2,
        "xor6_div2": (byte ^ 0x06) / 2,
        "bit_0": (byte >> 0) & 1,
        "bit_1": (byte >> 1) & 1,
        "bit_2": (byte >> 2) & 1,
        "bit_3": (byte >> 3) & 1,
        "bit_4": (byte >> 4) & 1,
        "bit_5": (byte >> 5) & 1,
        "bit_6": (byte >> 6) & 1,
        "bit_7": (byte >> 7) & 1,
    }

def find_candidates_ordered(packets, known_fields, field_map):
    claimed = extract_claimed_fields(field_map)
    num_bytes = len(packets[0])
    results = {k: [] for k in known_fields}

    def transform_series(byte_idx, transform_name):
        try:
            return [round(apply_bitwise_candidates(p[byte_idx])[transform_name], 2) for p in packets]
        except Exception:
            return []

    def count_state_changes(series):
        return sum(a != b for a, b in zip(series, series[1:]))

    for field_name, field_data in known_fields.items():
        expected_seq = field_data["values"]
        expected_set = set(expected_seq)
        expected_changes = count_state_changes(expected_seq)

        for byte_index in range(num_bytes):
            if any((byte_index, f["label"]) in claimed for f in field_map.get(byte_index, [])):
                continue

            for transformation in apply_bitwise_candidates(0).keys():
                series = transform_series(byte_index, transformation)
                series_set = set(series)

                if not expected_set.issubset(series_set):
                    continue

                actual_changes = count_state_changes(series)
                if actual_changes >= expected_changes:
                    results[field_name].append({
                        "byte_index": byte_index,
                        "transformation": transformation,
                        "matches": True,
                        "actual_changes": actual_changes,
                        "expected_changes": expected_changes
                    })

    return results


def find_candidates(packets, known_values, field_map):
    claimed = extract_claimed_fields(field_map)
    num_bytes = len(packets[0])
    results = {k: [] for k in known_values}

    for field_name, data in known_values.items():
        expected_values = set(data["values"])
        for byte_index in range(num_bytes):
            if any((byte_index, f["label"]) in claimed for f in field_map.get(byte_index, [])):
                continue

            seen_transforms = {}
            for transformation in [
                "identity", "xor_1", "xor_2", "xor_6", "div2", "xor2_div2", "xor6_div2",
                "bit_0", "bit_1", "bit_2", "bit_3", "bit_4", "bit_5", "bit_6", "bit_7"
            ]:
                try:
                    values = set(round(apply_bitwise_candidates(packet[byte_index])[transformation], 2) for packet in packets)
                    if expected_values.issubset(values):
                        seen_transforms[transformation] = values
                except Exception:
                    continue

            for tform in seen_transforms:
                results[field_name].append((byte_index, tform))

    return results

# Run analysis
csv_path = "1747660197.24942-debug_messages.csv"
packets = load_csv(csv_path)
candidates = find_candidates_ordered(packets, KNOWN_FIELDS, FIELD_MAP)

for field, matches in candidates.items():
    print(f"### Candidate Matches for `{field}`:")
    if matches:
        for match in matches:
            print(f"- Byte {match['byte_index']}: `{match['transformation']}` has {match['actual_changes']} changes (expected ≥ {match['expected_changes']})")
    else:
        print("- No strong candidates found.")
    print()
