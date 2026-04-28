#!/usr/bin/env python3
"""
Modify a Mermaid-generated sequence diagram SVG:
  1. Makes actor lifelines (downlines) dashed.
  2. For each BARE <rect class="rect"> (NOT inside a <g> — these are user-drawn
     sub-grouping rects, NOT Mermaid box elements):
       - Adds a stroke exactly matching the box elements' inline stroke style.
       - Asks for a custom annotation label to place at top-left.
       - When a label is given, the badge is placed at the normal height (top of the rect).
       - *Dynamic Shift*: All elements, arrows, paths, and notes below the badge 
         are shifted downwards by the badge height. Any encompassing boxes or 
         dashed lifelines are automatically extended to accommodate the shift.
  3. For each bold text element (class="noteText" or inline font-weight >=600):
       - Shows the text content and asks whether to remove the bold.

Usage:
    python modify_mermaid_svg4.py input.svg output.svg
"""

import sys
import re

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Stroke copied verbatim from the Mermaid box-element inline attributes.
BOX_STROKE_ATTRS = 'stroke="rgba(0,0,0,0.5)" stroke-width="2"'

# Height of the annotation polygon badge
BADGE_H = 35


# ─────────────────────────────────────────────────────────────────────────────
# 1. Make actor lifelines dashed
# ─────────────────────────────────────────────────────────────────────────────

def make_lifelines_dashed(svg: str):
    count = 0

    def replace_lifeline(m):
        nonlocal count
        tag = m.group(0)
        if "stroke-dasharray" in tag:
            return tag
        tag = re.sub(r'\s*stroke-width="[^"]*"', '', tag)
        tag = tag.rstrip("/>").rstrip()
        tag += ' stroke-dasharray="6,4" stroke-width="1.5px"/>'
        count += 1
        return tag

    pattern = re.compile(r'<line\b[^>]*class="[^"]*actor-line[^"]*"[^>]*/>', re.DOTALL)
    svg = pattern.sub(replace_lifeline, svg)
    return svg, count


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_attr(tag: str, name: str) -> str | None:
    m = re.search(rf'\b{name}="([^"]+)"', tag)
    return m.group(1) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# 2. Dynamic Shift Logic
# ─────────────────────────────────────────────────────────────────────────────

def shift_svg_down(svg: str, y_threshold: float, delta: float) -> str:
    """
    Parses the SVG and adds `delta` to any Y coordinate that is strictly 
    greater than `y_threshold`. This dynamically translates downstream elements 
    and extends the heights/bottoms of boxes and lifelines.
    """
    epsilon = 0.001  # Prevent floating point boundary issues

    def replace_attr(attr, new_val, t):
        # Format as float but cleanly without excess decimals
        return re.sub(rf'\b{attr}="[^"]*"', f'{attr}="{new_val:g}"', t)

    def update_tag(m):
        tag = m.group(0)

        # 1. transform="translate(x, y)"
        tr_m = re.search(r'\btransform="translate\(([^,]+),\s*([^\)]+)\)"', tag)
        if tr_m:
            x_val, y_val = float(tr_m.group(1)), float(tr_m.group(2))
            if y_val > y_threshold + epsilon:
                tag = tag[:tr_m.start()] + f'transform="translate({x_val:g}, {(y_val + delta):g})"' + tag[tr_m.end():]

        # 2. Path data `d="..."`
        d_m = re.search(r'\bd="([^"]+)"', tag)
        if d_m:
            d_str = d_m.group(1)
            def repl_d(match):
                x, y = match.group(1), match.group(2)
                y_val = float(y)
                if y_val > y_threshold + epsilon:
                    y_val += delta
                return f"{x},{y_val:g}"
            # Replaces coordinate pairs: X,Y
            new_d = re.sub(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', repl_d, d_str)
            tag = tag[:d_m.start()] + f'd="{new_d}"' + tag[d_m.end():]

        # 3. Polygon / Polyline `points="..."`
        points_m = re.search(r'\bpoints="([^"]+)"', tag)
        if points_m:
            pts_str = points_m.group(1)
            def repl_pts(match):
                x, y = match.group(1), match.group(2)
                y_val = float(y)
                if y_val > y_threshold + epsilon:
                    y_val += delta
                return f"{x},{y_val:g}"
            new_pts = re.sub(r'(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)', repl_pts, pts_str)
            tag = tag[:points_m.start()] + f'points="{new_pts}"' + tag[points_m.end():]

        # 4. Rectangles, SVGs, and Images (y and height)
        y_m = re.search(r'\by="([^"]+)"', tag)
        h_m = re.search(r'\bheight="([^"]+)"', tag)
        if y_m and h_m:
            try:
                old_y = float(y_m.group(1))
                old_h = float(h_m.group(1))
                old_bottom = old_y + old_h
                
                # Top edge shifts if it's below the threshold
                new_y = old_y + delta if old_y > y_threshold + epsilon else old_y
                # Bottom edge shifts if it's below the threshold
                new_bottom = old_bottom + delta if old_bottom > y_threshold + epsilon else old_bottom
                new_h = new_bottom - new_y
                
                tag = replace_attr("y", new_y, tag)
                tag = replace_attr("height", new_h, tag)
            except ValueError:
                pass
        elif y_m:
            # Standalone y (e.g. text)
            try:
                old_y = float(y_m.group(1))
                if old_y > y_threshold + epsilon:
                    tag = replace_attr("y", old_y + delta, tag)
            except ValueError:
                pass
        elif h_m and tag.startswith("<svg"):
            # Master SVG height tag
            try:
                old_h = float(h_m.group(1))
                tag = replace_attr("height", old_h + delta, tag)
            except ValueError:
                pass

        # 5. Lines (y1 and y2)
        for attr in ["y1", "y2"]:
            a_m = re.search(rf'\b{attr}="([^"]+)"', tag)
            if a_m:
                try:
                    old_y = float(a_m.group(1))
                    if old_y > y_threshold + epsilon:
                        tag = replace_attr(attr, old_y + delta, tag)
                except ValueError:
                    pass
        
        # 6. viewBox
        vb_m = re.search(r'\bviewBox="([^"]+)"', tag)
        if vb_m:
            parts = vb_m.group(1).split()
            if len(parts) == 4:
                try:
                    vx, vy, vw, vh = map(float, parts)
                    n_vy = vy + delta if vy > y_threshold + epsilon else vy
                    n_bottom = vy + vh
                    n_bottom = n_bottom + delta if n_bottom > y_threshold + epsilon else n_bottom
                    n_vh = n_bottom - n_vy
                    tag = tag[:vb_m.start()] + f'viewBox="{vx:g} {n_vy:g} {vw:g} {n_vh:g}"' + tag[vb_m.end():]
                except ValueError:
                    pass

        return tag

    return re.sub(r'<[^>]+>', update_tag, svg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Find and classify rect elements
# ─────────────────────────────────────────────────────────────────────────────

def find_bare_rects(svg: str) -> list:
    """
    Return all <rect class="rect"> elements NOT immediately inside a <g> tag.
    Those inside <g> are Mermaid's own box elements and are skipped.
    """
    pattern = re.compile(r'<rect\b[^>]*class="rect"[^>]*/>', re.DOTALL)
    results = []
    for m in pattern.finditer(svg):
        before = svg[max(0, m.start() - 4) : m.start()]
        if before.rstrip().endswith("<g>"):
            continue

        tag = m.group(0)
        x   = float(_get_attr(tag, "x") or 0)
        y   = float(_get_attr(tag, "y") or 0)
        w   = float(_get_attr(tag, "width") or 0)
        h   = float(_get_attr(tag, "height") or 0)

        rest        = svg[m.end() : m.end() + 400]
        lm          = re.search(r'<tspan[^>]*>([^<]+)</tspan>', rest)
        nearby_label = lm.group(1).strip() if lm else "(no nearby label)"

        results.append({
            "start":        m.start(),
            "end":          m.end(),
            "full_match":   tag,
            "nearby_label": nearby_label,
            "x": x, "y": y, "w": w, "h": h,
        })
    return results


# ─────────────────────────────────────────────────────────────────────────────
# 3a. Stroke + annotation
# ─────────────────────────────────────────────────────────────────────────────

def _add_stroke_to_rect(rect_tag: str) -> str:
    rect_tag = re.sub(r'\s*stroke(?:-width|-dasharray)?="[^"]*"', '', rect_tag)
    rect_tag = rect_tag.rstrip("/>").rstrip()
    rect_tag += f' {BOX_STROKE_ATTRS}/>'
    return rect_tag


def _build_annotation(x: float, y: float, label: str) -> str:
    bw    = 50 + max(0, len(label) - 3) * 8
    notch = 8
    pts   = (
        f"{x},{y} {x+bw},{y} "
        f"{x+bw},{y+BADGE_H-notch} {x+bw-notch},{y+BADGE_H} {x},{y+BADGE_H}"
    )
    cx, cy = x + bw / 2, y + BADGE_H / 2
    return (
        f'<polygon points="{pts}" class="labelBox"/>'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'dominant-baseline="middle" alignment-baseline="middle" '
        f'style="font-family: &quot;Open Sans Variable&quot;, sans-serif; '
        f'font-size: 16px; font-weight: 400;" '
        f'class="labelText">{label}</text>'
    )


def process_bare_rects(svg: str, rects: list) -> str:
    decisions = []

    for idx, r in enumerate(rects, 1):
        print(
            f"\n  Bare rect {idx}: '{r['nearby_label']}' "
            f"(x={r['x']:.0f}, y={r['y']:.0f}, w={r['w']:.0f}, h={r['h']:.0f})"
        )
        print(f"    Will add stroke: {BOX_STROKE_ATTRS}")
        label = input("    Annotation label (leave blank to skip): ").strip()
        decisions.append(label)

    # Process forward (top to bottom) so coordinate shifts are compounded logically
    for i, label in enumerate(decisions):
        if not label:
            current_rects = find_bare_rects(svg)
            r = current_rects[i]
            new_tag = _add_stroke_to_rect(r["full_match"])
            svg = svg[: r["start"]] + new_tag + svg[r["end"] :]
            print(f"  + Stroked bare rect at x={r['x']:.0f} (no annotation)")
            continue

        # Re-parse to get the current Y coordinates (in case earlier iterations shifted them)
        current_rects = find_bare_rects(svg)
        r = current_rects[i]
        badge_y = r["y"]

        # 1. Apply downstream shift to everything physically below the insertion point
        svg = shift_svg_down(svg, badge_y, BADGE_H)

        # 2. Re-parse because shift_svg_down modified the SVG string offsets & heights
        current_rects_after = find_bare_rects(svg)
        r_after = current_rects_after[i]

        # 3. Add stroke to rect and safely append annotation at original normal height
        new_tag = _add_stroke_to_rect(r_after["full_match"])
        annotation = _build_annotation(r_after["x"], badge_y, label)

        svg = svg[: r_after["start"]] + new_tag + annotation + svg[r_after["end"] :]
        print(f"  + Added annotation '{label}' and shifted downstream elements down by {BADGE_H}px")

    return svg


# ─────────────────────────────────────────────────────────────────────────────
# 4. Bold text — ask to remove
# ─────────────────────────────────────────────────────────────────────────────

def find_bold_texts(svg: str) -> list:
    results    = []
    seen_spans = set()
    pattern    = re.compile(
        r'<text\b[^>]*(?:class="[^"]*noteText[^"]*"|'
        r'style="[^"]*font-weight\s*:\s*(?:bold|[6-9]\d\d)[^"]*")[^>]*>'
        r'(.*?)</text>',
        re.DOTALL,
    )
    for m in pattern.finditer(svg):
        if m.start() in seen_spans:
            continue
        seen_spans.add(m.start())
        inner = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        results.append({
            "start": m.start(),
            "end":   m.end(),
            "full":  m.group(0),
            "text":  inner or "(empty)",
        })
    return results


def _remove_bold_from_element(tag_str: str) -> str:
    tag_str = re.sub(
        r'\bclass="([^"]*)\bnoteText\b([^"]*)"',
        lambda m: f'class="{(m.group(1) + m.group(2)).strip()}"',
        tag_str,
    )
    tag_str = re.sub(r'(font-weight\s*:\s*)(?:bold|[6-9]\d\d)', r'\g<1>400', tag_str)
    return tag_str


def process_bold_texts(svg: str, bolds: list) -> str:
    decisions = []
    for idx, b in enumerate(bolds, 1):
        print(f"\n  Bold text {idx}: \"{b['text']}\"")
        ans = input("    Remove bold? [y/N]: ").strip().lower()
        decisions.append(ans == "y")

    for b, remove in reversed(list(zip(bolds, decisions))):
        if not remove:
            continue
        svg = svg[: b["start"]] + _remove_bold_from_element(b["full"]) + svg[b["end"] :]
        print(f"  + Removed bold from \"{b['text']}\"")

    return svg


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage: python modify_mermaid_svg4.py input.svg")
        sys.exit(1)

    input_path = sys.argv[1]
    pdf_path = input_path.rsplit(".", 1)[0] + ".pdf"

    print(f"\nReading '{input_path}' ...")
    with open(input_path, "r", encoding="utf-8") as f:
        svg = f.read()

    # Step 1
    print("\n[1] Making actor lifelines dashed ...")
    svg, n = make_lifelines_dashed(svg)
    print(f"  -> {n} lifeline(s) made dashed.")

    # Step 2
    print("\n[2] Processing BARE grouping rects (stroke + annotation) ...")
    bare_rects = find_bare_rects(svg)
    print(f"  Found {len(bare_rects)} bare rect(s) (Mermaid box elements excluded).")
    if bare_rects:
        svg = process_bare_rects(svg, bare_rects)

    # Step 3
    print("\n[3] Checking for bold text ...")
    bolds = find_bold_texts(svg)
    print(f"  Found {len(bolds)} bold text element(s).")
    if bolds:
        svg = process_bold_texts(svg, bolds)

    # Step 4: Convert to PDF
    try:
        import cairosvg
        print(f"\nConverting to PDF: '{pdf_path}' ...")
        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=pdf_path)
        print(f"PDF written to '{pdf_path}'\n")
    except ImportError:
        print("cairosvg not installed — skipping PDF conversion. Run: pip install cairosvg")


if __name__ == "__main__":
    main()