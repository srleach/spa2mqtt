import csv

def xor(v, k): return v ^ k
def shl(v, b): return (v << b) & 0xFF
def shr(v, b): return v >> b
def identity(v): return v

def generate_transformations(raw_value):
    for xor_val in range(256):
        x = xor(raw_value, xor_val)
        yield f"XOR {xor_val}", x
        for shift in range(1, 4):
            yield f"XOR {xor_val} → SHL {shift}", shl(x, shift)
            yield f"XOR {xor_val} → SHR {shift}", shr(x, shift)
    for shift in range(1, 4):
        yield f"SHL {shift}", shl(raw_value, shift)
        yield f"SHR {shift}", shr(raw_value, shift)
    yield "IDENTITY", raw_value

def load_csv(path):
    with open(path, newline='') as f:
        return [list(map(int, row)) for row in csv.reader(f)]

def expand_expected_outputs(observation, total_rows):
    default = observation.get("default")
    overrides = observation.get("overrides", {})
    return [(i, overrides.get(i, default)) for i in range(total_rows)]

def find_field_matches(rows, expected_outputs):
    num_fields = len(rows[0])
    matches = {}

    for field_index in range(num_fields):
        candidates = []

        for row_index, expected in expected_outputs:
            raw_val = rows[row_index][field_index]
            for label, result in generate_transformations(raw_val):
                if result == expected:
                    candidates.append(label)
                    break
            else:
                break  # No match for this field in this row
        else:
            # all expected outputs matched
            matches[field_index] = candidates

    return matches

# --- Usage Example ---

csv_path = "debug_messages_old.csv"
rows = load_csv(csv_path)
total_rows = len(rows)

water_life = {
    "default": 0x78,
    "overrides": {
        # 5: 93,
        # 10: 92,
    }
}

expected = expand_expected_outputs(water_life, total_rows)
result = find_field_matches(rows, expected)

print("\n🔍 Matching candidates for 'water_life':")
for index, transforms in result.items():
    print(f"Byte {index}: transforms → {set(transforms)}")
