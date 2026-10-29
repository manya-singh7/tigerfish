"""The How it works pipeline diagram as SVG (docs/DESIGN.md palette).

The app draws it inline (tigerfish/ui/pages.py) so it takes the page's fonts and theme
colours from class names styled in tigerfish/ui/style.py; scripts/build_brand.py writes the
standalone assets/how_it_works.svg, which carries its own styles.
"""

TEAL, INK, PAPER, MUTED = "#0D4242", "#17302F", "#F2ECDF", "#59625F"

W = 720
STAGES = [
    ("EIA report (PDF)", ["Hundreds of pages: text, scans, tables, maps"], None),
    ("Read selected pages", ["Text pages: the text layer, read by Lightning",
                         "Scans, tables, maps: Super-VL reads the image"], "Lightning, Super-VL"),
    ("Extract claims", ["Checkable statements, with their page numbers"], "Lightning, Super-VL"),
    ("Pair claims", ["Statements on the same topic that could disagree"], None),
    ("Triage", ["Drop pairs that clearly agree"], "Lightning"),
    ("Verdicts", ["Read both passages in full; decide and say why"], "Ultra"),
]
SIDE = [("Species", "GBIF records against the species listed"),
        ("Web evidence", "Tavily search and the paper trail"),
        ("Accreditation", "Is the consultant NABET-accredited?"),
        ("ToR promises", "Did the report do what the ToR asked?")]
OUTPUTS = [("Flags", ["Each quotes the report with its page, so anyone can check it"]),
           ("Human review", ["A person confirms or rejects every flag"]),
           ("Letter and RTI pack", ["Built only from confirmed flags"])]


def diagram_svg(standalone=False) -> str:
    out, y, gap = [], 20, 34

    def box(y, title, lines, model=None, x=20, w=W - 40):
        h = 54 + 26 * len(lines)
        s = [f'<rect class="d-box" x="{x}" y="{y}" width="{w}" height="{h}" rx="3"/>',
             f'<text class="d-title" x="{x + 20}" y="{y + 34}">{title}</text>']
        if model:
            s.append(f'<text class="d-model" x="{x + w - 20}" y="{y + 34}" '
                     f'text-anchor="end">{model}</text>')
        for i, line in enumerate(lines):
            s.append(f'<text class="d-body" x="{x + 20}" y="{y + 62 + 26 * i}">{line}</text>')
        return s, h

    def arrow(y1, y2):
        x = W / 2
        return [f'<line class="d-line" x1="{x}" y1="{y1}" x2="{x}" y2="{y2 - 2}"/>',
                f'<path class="d-head" d="M{x - 6} {y2 - 10} L{x} {y2} L{x + 6} {y2 - 10}"/>']

    for i, (t, lines, model) in enumerate(STAGES):
        if i:
            out += arrow(y - gap, y)
        s, h = box(y, t, lines, model)
        out += s
        y += h + gap
    out += arrow(y - gap, y)
    band_top = y
    out.append(f'<text class="d-title" x="20" y="{y + 24}">Side checks, alongside the steps above</text>')
    y += 44
    cw = (W - 40 - 16) / 2
    for i, (t, line) in enumerate(SIDE):
        x = 20 + (i % 2) * (cw + 16)
        yy = y + (i // 2) * 96
        out += [f'<rect class="d-box" x="{x}" y="{yy}" width="{cw}" height="80" rx="3"/>',
                f'<text class="d-title" x="{x + 18}" y="{yy + 32}">{t}</text>',
                f'<text class="d-body" x="{x + 18}" y="{yy + 60}">{line}</text>']
    y += 2 * 96 - 16
    out.insert(len(out) - 13, f'<rect class="d-dash" x="8" y="{band_top - 8}" width="{W - 16}" '
                              f'height="{y - band_top + 24}" rx="3"/>')
    y += 16 + gap
    for t, lines in OUTPUTS:
        out += arrow(y - gap, y)
        s, h = box(y, t, lines)
        if t == "Flags":
            s[0] = s[0].replace('class="d-box"', 'class="d-box d-key"')
        out += s
        y += h + gap
    total = y - gap + 20
    style = ""
    if standalone:
        style = (f"<style>.d-box{{fill:{PAPER};stroke:{TEAL};stroke-width:1}}"
                 f".d-key{{stroke-width:2}}.d-dash{{fill:none;stroke:{MUTED};stroke-width:1;"
                 f"stroke-dasharray:5 5}}.d-line,.d-head{{fill:none;stroke:{TEAL};stroke-width:1.5}}"
                 f".d-title{{font:600 22px Newsreader,Georgia,serif;fill:{INK}}}"
                 f".d-body{{font:400 17px 'Schibsted Grotesk',Arial,sans-serif;fill:{MUTED}}}"
                 f".d-model{{font:500 15px 'IBM Plex Mono',Consolas,monospace;fill:{TEAL}}}</style>"
                 f'<rect width="{W}" height="{total}" fill="{PAPER}"/>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" class="tf-diagram" viewBox="0 0 {W} {total}" '
            f'role="img" aria-label="How TigerFish works: from the PDF to flags a person checks">'
            + style + "".join(out) + "</svg>\n")
