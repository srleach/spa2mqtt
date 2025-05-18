import csv
import sys

with open("debug_messages.csv", "r", newline="") as f:
    reader = csv.reader(f)
    for row in reader:
        # In this context, row is a single
        print(row)  # row is a list of strings

        sys.exit(1)
