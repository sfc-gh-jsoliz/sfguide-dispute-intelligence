"""WCAG AA contrast check for the Rebuttra design tokens (docs/DESIGN.md)."""
import sys


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


LIGHT = {"canvas": "#EDF1F2", "paper": "#FFFFFF", "paper-2": "#F5F8F8"}
PAIRS = [(fg, bg) for fg in ("#102326", "#4E6064", "#11757B", "#11795B", "#A33A12", "#4B4FA6",
                             "#55606B", "#7A6A2E", "#6B5512", "#0E6E7E") for bg in LIGHT.values()]
PAIRS += [("#11795B", "#DDF3EA"), ("#A33A12", "#FBE5DA"), ("#4B4FA6", "#E6E7F7"), ("#55606B", "#ECEEF0"),
          ("#FFFFFF", "#0C3B3E"), ("#FFFFFF", "#134A4E"), ("#FFFFFF", "#11757B"), ("#3FD3A1", "#0C3B3E"),
          ("#C9DCDD", "#0C3B3E")]
DARK = {"canvas": "#0A1C1E", "paper": "#102A2D"}
PAIRS += [(fg, bg) for fg in ("#E4EEEE", "#9DB3B5", "#4FC3C9", "#3FD3A1", "#F08A5D") for bg in DARK.values()]

bad = 0
for fg, bg in PAIRS:
    r = ratio(fg, bg)
    ok = r >= 4.5
    bad += not ok
    print(f"{fg} on {bg}: {r:5.2f} {'pass' if ok else 'FAIL'}")
print("all pass" if not bad else f"{bad} fail")
sys.exit(1 if bad else 0)
