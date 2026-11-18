"""Draw the detail sketches (round 2): tower details and the deck truss, enlarged.

Run from the repo root:
    uvx --with matplotlib python projects/hobby/cad-apprentice/demos/suspension-bridge/scripts/sketch_details.py

Uses the sizes in sketch.py. Writes PNGs 4 and 5 to sketches/. Where a size is a design choice and not
from a source, the label says so.
"""
from matplotlib.patches import Polygon, Rectangle
import matplotlib.pyplot as plt

from sketch import (CELL, DECK_W, DIM, EL_ROAD_TOWER, GHOST, INK, OUT, S, SPACING, STEEL, STRUTS,
                    ROAD_STRUT, TIERS, TRUSS_D, dim_h, dim_v, tier_width, z)

LIGHT = "#e8836f"                # lit face of a flute
DARK = "#8e2a1e"                 # shaded face

# Detail sizes (mm). Sources in the README, § Detail sources.
FLUTE_PITCH = 1.3                # 1:400 model, read: 4.8 mm there
FLUTE_DEPTH = 0.4                # a design choice: deep enough to print, shallow enough to stay strong
LEDGE_H = 0.6                    # strut frame ledges, top and bottom; a design choice
LEDGE_OUT = 0.4                  # how far the ledges stand proud of the flutes; a design choice
FLUTED_SHARE = 0.65              # fluted band = upper 65 % of the strut face; HAER photo 12, read roughly
CORBEL = [(1.2, 0.6), (0.8, 0.6), (0.4, 0.6)]   # (out, tall) per step, top down; a design choice
BALCONY_OUT = 10 * S             # 10 ft past the leg's outer face, 45° underside; STR
STRUT_THICK = 5 * CELL * S       # strut thickness along the bridge (build parameter)

PANEL = 25 * S                   # floor beams and truss panels every 25 ft; STR
CHORD = 0.8                      # truss chord height; a design choice (printable)
MEMBER = 0.6                     # truss verticals and diagonals; a design choice
WALL = 0.8                       # truss wall thickness; a design choice
SLAB = 1.0                       # road slab; a design choice
RIB = (1.5, 0.6)                 # floor-beam rib under the slab (deep, thick); a design choice
RAIL_H = 0.8                     # railing lip; height not found in a source, a design choice
CURB_H = 0.3                     # sidewalk step above the road; a design choice
SIDEWALK = 10 * S                # GGB
ROADWAY = 62 * S                 # GGB


def leg_plan(across, along):
    """A tier's plan as a stepped cross: list of (along, across) rectangles in cells.

    The base matches Plate VI (15x5, 9x7, 4x9 cells). The top is a plain 3x7 (STR). The tiers in
    between follow the same rule; that rule is a design choice."""
    def r(v):
        return round(v * 2) / 2
    if across - 4 >= 1:
        return [(along, across - 4), (r(0.6 * along), across - 2), (r(0.27 * along), across)]
    if across - 2 >= 1.5:
        return [(along, across - 2), (r(0.5 * along), across)]
    return [(along, across)]


def front_leg(ax, xc, el0, el1, across, along, outer):
    """A leg tier seen looking along the road: full width plus the arm edges as lines."""
    w = across * CELL * S
    ax.add_patch(Rectangle((xc - w / 2, z(el0)), w, z(el1) - z(el0), fc=STEEL, ec=INK, lw=0.8))
    for _, a in leg_plan(across, along)[:-1]:
        for sgn in (-1, 1):
            x = xc + sgn * a * CELL * S / 2
            ax.plot([x, x], [z(el0), z(el1)], color=DARK, lw=0.6)


def step_cap(ax, xc, el, w_low, w_high):
    """45° slope where the leg steps narrower (Plate VIII)."""
    run = (w_low - w_high) / 2
    for sgn in (-1, 1):
        x_out, x_in = xc + sgn * w_low / 2, xc + sgn * w_high / 2
        ax.add_patch(Polygon([(x_out, z(el)), (x_in, z(el) + run), (x_in, z(el))],
                             fc=LIGHT, ec=INK, lw=0.6))


def fluted_strut(ax, x0, x1, el0, el1):
    y0, y1 = z(el0), z(el1)
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc=STEEL, ec=INK, lw=0.8))
    for yb in (y0, y1 - LEDGE_H):                      # frame ledges
        ax.add_patch(Rectangle((x0, yb), x1 - x0, LEDGE_H, fc=LIGHT, ec=INK, lw=0.5))
    band0 = y1 - LEDGE_H - (y1 - y0 - 2 * LEDGE_H) * FLUTED_SHARE
    n = int((x1 - x0) / FLUTE_PITCH)
    pad = (x1 - x0 - n * FLUTE_PITCH) / 2
    for i in range(n):                                 # sawtooth flutes: lit half, shaded half
        xa = x0 + pad + i * FLUTE_PITCH
        ax.add_patch(Rectangle((xa, band0), FLUTE_PITCH / 2, y1 - LEDGE_H - band0, fc=LIGHT, ec="none"))
        ax.add_patch(Rectangle((xa + FLUTE_PITCH / 2, band0), FLUTE_PITCH / 2, y1 - LEDGE_H - band0,
                               fc=DARK, ec="none"))
    ax.add_patch(Rectangle((x0 + 0.5, y0 + LEDGE_H + 0.3), x1 - x0 - 1.0, band0 - y0 - LEDGE_H - 0.6,
                           fc="none", ec=DARK, lw=0.6))   # plain recessed panel
    for sgn, xe in ((1, x0), (-1, x1)):                # stepped corbels under each end
        top = y0
        for out, tall in CORBEL:
            ax.add_patch(Rectangle((xe if sgn > 0 else xe - out, top - tall), out, tall,
                                   fc=STEEL, ec=INK, lw=0.5))
            top -= tall


def tier_close_up(ax):
    half = SPACING * S / 2
    el_lo, el_hi = 200, 545
    (t1, t2, t3) = TIERS[0], TIERS[1], TIERS[2]
    for xc, outer in ((-half, -1), (half, 1)):
        for el0, el1, across, along in (t1, t2, t3):
            front_leg(ax, xc, max(el0, el_lo), min(el1, el_hi), across, along, outer)
        step_cap(ax, xc, t1[1], t1[2] * CELL * S, t2[2] * CELL * S)
        step_cap(ax, xc, t2[1], t2[2] * CELL * S, t3[2] * CELL * S)
        step_cap(ax, xc, t3[1], t3[2] * CELL * S, TIERS[3][2] * CELL * S)
        front_leg(ax, xc, t3[1], el_hi, TIERS[3][2], TIERS[3][3], outer)
        # balcony on the outer face at road level, 45° underside (STR)
        xf = xc + outer * tier_width(EL_ROAD_TOWER) / 2
        xo = xf + outer * BALCONY_OUT
        ax.add_patch(Polygon([(xf, z(EL_ROAD_TOWER)), (xo, z(EL_ROAD_TOWER)),
                              (xo, z(EL_ROAD_TOWER) - 0.6), (xf, z(EL_ROAD_TOWER) - 0.6 - BALCONY_OUT)],
                             fc=LIGHT, ec=INK, lw=0.6))
    w = tier_width(ROAD_STRUT[1] - 1)
    ax.add_patch(Rectangle((-half + w / 2, z(ROAD_STRUT[0])), 2 * half - w, z(ROAD_STRUT[1]) - z(ROAD_STRUT[0]),
                           fc=STEEL, ec=INK, lw=0.8))
    for el0_, el1_ in (STRUTS[2], STRUTS[3]):
        w = tier_width(el0_ - 1)
        fluted_strut(ax, -half + w / 2, half - w / 2, el0_, el1_)
    el0, el1 = STRUTS[3]
    w = tier_width(el0 - 1)
    ax.add_patch(Rectangle((-half, z(EL_ROAD_TOWER - TRUSS_D)), 2 * half, TRUSS_D * S,
                           fc="none", ec=GHOST, lw=1, ls="--"))
    ax.text(0, z(EL_ROAD_TOWER - TRUSS_D / 2), "deck, end on", color=GHOST, fontsize=7, ha="center", va="center")

    def note(xy, xytext, text):
        ax.annotate(text, xy, xytext, fontsize=7, color=DIM, va="center",
                    arrowprops=dict(arrowstyle="-", color=DIM, lw=0.5))
    xr = half + 9
    note((half - w / 2 - 2, z(el1) - 1.2), (xr, z(el1) + 3), f"flutes {FLUTE_PITCH} mm apart,\n{FLUTE_DEPTH} mm deep")
    note((half - w / 2 - 2, z(el0) + 1.2), (xr, z(el0) + 0.5), "plain recessed panel")
    note((half - w / 2 - 0.3, z(el0) - 1), (xr, z(el0) - 4), "3-step corbel")
    note((half + tier_width(STRUTS[3][1] - 1) / 2 - 0.2, z(STRUTS[3][1]) + 0.3), (xr, z(STRUTS[3][1]) + 9),
         "leg steps in, 45° cap")
    note((half + tier_width(EL_ROAD_TOWER) / 2 + BALCONY_OUT / 2, z(EL_ROAD_TOWER) - 1), (xr, z(EL_ROAD_TOWER) - 6),
         f"balcony {BALCONY_OUT:.1f} mm out,\n45° underside")
    note((half - 0.3, z(300)), (xr, z(300)), "lines = edges of the\nleg's stepped cross")
    dim_v(ax, -half - tier_width(300) / 2 - 3, z(el0), z(el1), f"{z(el1) - z(el0):.1f}", side=-1)
    ax.set_title("4a. Road level up to the 2nd portal strut,\nlooking along the road (enlarged)",
                 fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-half - 10, half + 26)
    ax.set_ylim(z(el_lo), z(el_hi))
    ax.axis("off")


def leg_plans(ax):
    x = 0.0
    for i, (el0, el1, across, along) in enumerate(TIERS, 1):
        rects = leg_plan(across, along)
        for a_len, a_w in rects:
            ax.add_patch(Rectangle((x - a_len * CELL * S / 2, -a_w * CELL * S / 2), a_len * CELL * S,
                                   a_w * CELL * S, fc=STEEL, ec="none"))
        for a_len, a_w in rects:
            ax.add_patch(Rectangle((x - a_len * CELL * S / 2, -a_w * CELL * S / 2), a_len * CELL * S,
                                   a_w * CELL * S, fc="none", ec=INK, lw=0.6))
        ax.text(x, -4.6, f"tier {i}\n{along * CELL * S:.1f} × {across * CELL * S:.1f}", fontsize=7,
                color=DIM, ha="center", va="top")
        x += along * CELL * S / 2 + 6 + (TIERS[i][3] * CELL * S / 2 if i < len(TIERS) else 0)
    ax.text(0, 5.2, "base: Plate VI", fontsize=6.5, color=DIM, ha="center")
    ax.text(x - 6 - TIERS[-1][3] * CELL * S / 2, 5.2, "top: plain, STR", fontsize=6.5, color=DIM, ha="center")
    ax.set_title("4b. Leg plans, tier 1 (base) to tier 5 (top), mm; along the bridge →", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-8, x)
    ax.set_ylim(-7.5, 6.5)
    ax.axis("off")


def flute_section(ax):
    """Cut through a strut, seen from above: flutes on both faces."""
    length = 6 * FLUTE_PITCH
    t = STRUT_THICK
    pts_top, pts_bot = [], []
    for i in range(7):
        x = i * FLUTE_PITCH
        pts_top += [(x, t / 2), (x + FLUTE_PITCH, t / 2 - FLUTE_DEPTH)] if i < 6 else [(x, t / 2)]
        pts_bot += [(x, -t / 2), (x + FLUTE_PITCH, -t / 2 + FLUTE_DEPTH)] if i < 6 else [(x, -t / 2)]
    poly = pts_top + [(length, -t / 2)] + pts_bot[::-1]
    ax.add_patch(Polygon(poly, fc=STEEL, ec=INK, lw=0.8))
    dim_h(ax, 0, FLUTE_PITCH, t / 2 + 0.5, f"{FLUTE_PITCH}")
    dim_v(ax, length + 0.6, -t / 2, t / 2, f"strut {t:.1f} thick")
    ax.text(length / 2, -t / 2 - 0.6, f"teeth {FLUTE_DEPTH} mm deep on both faces",
            fontsize=7, color=DIM, ha="center", va="top")
    ax.set_title("4c. Cut through a strut, from above (enlarged)", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-1, length + 6)
    ax.set_ylim(-t / 2 - 2.2, t / 2 + 2)
    ax.axis("off")


def sketch_tower():
    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.1, 1], height_ratios=[1, 1])
    tier_close_up(fig.add_subplot(gs[:, 0]))
    leg_plans(fig.add_subplot(gs[0, 1]))
    flute_section(fig.add_subplot(gs[1, 1]))
    fig.suptitle("4. Tower details (all sizes in mm at the print size, towers 150 mm)", fontsize=12)
    fig.savefig(OUT / "4-tower-details.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def deck_side(ax, panels=4):
    d = TRUSS_D * S
    L = panels * PANEL
    ax.add_patch(Rectangle((0, d - CHORD), L, CHORD, fc=STEEL, ec=INK, lw=0.6))   # top chord
    ax.add_patch(Rectangle((0, 0), L, CHORD, fc=STEEL, ec=INK, lw=0.6))           # bottom chord
    for i in range(panels + 1):                                                   # verticals
        x = min(max(i * PANEL - MEMBER / 2, 0), L - MEMBER)
        ax.add_patch(Rectangle((x, CHORD), MEMBER, d - 2 * CHORD, fc=STEEL, ec=INK, lw=0.5))
    for i in range(panels):                                                       # Warren diagonals
        xa, xb = i * PANEL, (i + 1) * PANEL
        (p, q) = ((xa, CHORD), (xb, d - CHORD)) if i % 2 == 0 else ((xa, d - CHORD), (xb, CHORD))
        ax.plot([p[0], q[0]], [p[1], q[1]], color=STEEL, lw=MEMBER * 7.5, solid_capstyle="butt")
        ax.plot([p[0], q[0]], [p[1], q[1]], color=INK, lw=0.3)
    ax.add_patch(Rectangle((0, d), L, RAIL_H, fc="none", ec=INK, lw=0.6, hatch="||||"))
    for i in range(0, panels + 1, 2):                                             # hangers, CAD only
        ax.plot([i * PANEL] * 2, [d + RAIL_H, d + 6], color=GHOST, lw=1, ls="--")
    dim_h(ax, 0, PANEL, -2.0, f"panel {PANEL:.2f}")
    dim_v(ax, L + 0.6, 0, d, f"truss {d:.2f} deep")
    ax.text(0, d + 6.4, "hangers every 2nd panel point (look-only in CAD)", fontsize=7, color=GHOST)
    ax.text(L / 2, d + RAIL_H + 0.4, f"railing lip {RAIL_H}", fontsize=7, color=DIM, ha="center")
    ax.text(L / 2 + 6, -1.6, "triangles are open holes through the side wall", fontsize=7, color=DIM, ha="center")
    ax.set_title("5a. Deck side, 4 panels (enlarged)", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-1, L + 8)
    ax.set_ylim(-4, d + 8)
    ax.axis("off")


def deck_end(ax):
    d = TRUSS_D * S
    half = DECK_W * S / 2
    for sgn in (-1, 1):                                                           # truss walls
        ax.add_patch(Rectangle((sgn * half - WALL / 2, 0), WALL, d, fc=STEEL, ec=INK, lw=0.6))
        ax.add_patch(Rectangle((sgn * half - WALL / 2, d), WALL, RAIL_H, fc=STEEL, ec=INK, lw=0.6))
        xs0 = sgn * (half - WALL / 2)                                             # sidewalk
        ax.add_patch(Rectangle((min(xs0, xs0 - sgn * SIDEWALK), d), SIDEWALK, CURB_H, fc="#bbb", ec=INK, lw=0.5))
    ax.add_patch(Rectangle((-half + WALL / 2, d - SLAB), 2 * half - WALL, SLAB, fc="#888", ec=INK, lw=0.6))
    ax.add_patch(Rectangle((-half + WALL / 2, d - SLAB - RIB[0]), 2 * half - WALL, RIB[0],
                           fc="none", ec=GHOST, lw=0.8, ls="--"))
    dim_h(ax, -half, half, -1.3, f"road_width {2 * half:.1f}")
    dim_h(ax, -ROADWAY / 2, ROADWAY / 2, d + 2.0, f"roadway {ROADWAY:.1f}")
    ax.text(half - WALL / 2 - SIDEWALK / 2, d + CURB_H + 0.3, f"sidewalk\n{SIDEWALK:.1f}", fontsize=6.5,
            color=DIM, ha="center", va="bottom")
    ax.text(0, d - SLAB - RIB[0] - 0.4, f"floor-beam rib under the slab at every panel point ({RIB[0]} deep)",
            fontsize=6.5, color=GHOST, ha="center", va="top")
    ax.text(0, -3.0, "prints upright, road on top: the slab and ribs bridge between the two truss walls",
            fontsize=7, color=DIM, ha="center")
    ax.set_title("5b. Deck end on (enlarged)", fontsize=10)
    ax.set_aspect("equal")
    ax.set_xlim(-half - 2, half + 2)
    ax.set_ylim(-4, d + 4)
    ax.axis("off")


def sketch_deck():
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 9), gridspec_kw=dict(height_ratios=[1, 1]))
    deck_side(a)
    deck_end(b)
    fig.suptitle("5. Deck details (mm at the print size)", fontsize=12)
    fig.savefig(OUT / "5-deck-details.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    sketch_tower()
    sketch_deck()
    print("wrote", OUT)
