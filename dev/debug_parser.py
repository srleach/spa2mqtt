import csv
import sys
from time import sleep

# Extended multi-field map
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
            "name": "Clearray Life Remain",
            "transform": lambda b: (b ^ 0xff) - 5,
            "label": "CR",
            "note": "XOR 0xFF, Sub 5"
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

def load_csv(path):
    with open(path, newline='') as f:
        return [list(map(int, row)) for row in csv.reader(f)]

def render_packet_markdown(packet, field_map, index):
    lines = []
    lines.append(f"### Packet {index}\n")
    lines.append("| Byte | Hex | Fields                                       | Decoded     | Transform(s)                                                                                 |")
    lines.append("|------|-----|----------------------------------------------|-------------|----------------------------------------------------------------------------------------------|")

    for i, byte in enumerate(packet):
        hex_val = f"{byte:02X}"
        fields = field_map.get(i, [])
        if fields:
            field_names = ", ".join(f["label"] for f in fields)
            decoded_vals = ", ".join(str(f["transform"](byte)) for f in fields)
            notes = ", ".join(f["note"] for f in fields)
            lines.append(f"| {i:>4} | {hex_val}  | {field_names:<44} | {decoded_vals:<11} | {notes:<92} |")
        else:
            lines.append(f"| {i:>4} | {hex_val}  |                  |             |                      |")

    return "\n".join(lines)

def main():
    csv_path = "1747660197.24942-debug_messages.csv"
    packets = load_csv(csv_path)

    # Show first 3 packets
    for i, packet in enumerate(packets):
        markdown = render_packet_markdown(packet, FIELD_MAP, i)
        print(markdown)
        print()
        sleep(0.5)

if __name__ == "__main__":
    main()
