"""Draw the confirmation sketches for the suspension bridge.

Run:
    uvx --with matplotlib python <kit>/demos/suspension-bridge/scripts/sketch.py

Real sizes are in feet and elevations in feet above water, as in the project README. They are
scaled so the tower (pier top to saddle top) is TOWER_HEIGHT mm. Writes PNGs to sketches/.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, FancyBboxPatch
import numpy as np

OUT = Path(__file__).resolve().parent.parent / "sketches"

# The two Customize favorites (mm)
TOWER_HEIGHT = 150.0
ROAD_WIDTH = None                # None = true to scale (90 ft)

# Real bridge (ft, elevations above water), README § The real bridge
EL_PIER = 44.0
EL_TOP = 746.0                   # saddle top
EL_LEG_TOP = 727.0               # leg steel under the saddle (Plate IX, read)
EL_ROAD_TOWER = 248.08
EL_ROAD_MID = 266.70
EL_CABLE_LOW = 276.0
MAIN_SPAN = 4200.0
SIDE_SPAN = 1125.41
DECK_W = 90.0                    # = cable spacing = leg spacing
TRUSS_D = 25.0
HANGER_PITCH = 50.0
CELL = 3.5
CABLE_D = 36.375 / 12

# Struts: (bottom, top) elevations, README § Strut heights (model column)
STRUTS = [(706, 727), (600, 632), (488, 522), (376, 408)]
ROAD_STRUT = (210, 225)
MID_STRUT = (132, 144)
BOTTOM_STRUT = (44, 60)

# Leg tiers: (from el., to el., cells across, cells along). The leg steps in just above
# the road strut and the first three portal struts; 9 x 15 cells at the base, 3 x 7 at the top.
TIERS = [
    (EL_PIER, ROAD_STRUT[1], 9, 15),
    (ROAD_STRUT[1], STRUTS[3][1], 7.5, 13),
    (STRUTS[3][1], STRUTS[2][1], 6, 11),
    (STRUTS[2][1], STRUTS[1][1], 4.5, 9),
    (STRUTS[1][1], EL_LEG_TOP, 3, 7),
]

S = TOWER_HEIGHT / (EL_TOP - EL_PIER)          # mm per ft
SPACING = (ROAD_WIDTH / S) if ROAD_WIDTH else DECK_W


def z(el):
    """Elevation in ft -> mm above the pier top."""
    return (el - EL_PIER) * S


INK = "#222"
STEEL = "#c0392b"                # the towers' colour
DIM = "#2c3e50"
GHOST = "#95a5a6"
WATER = "#d6eaf8"


def dim_v(ax, x, y0, y1, text, side=1):
    ax.annotate("", (x, y0), (x, y1), arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.8))
    ax.text(x + side * 1.2, (y0 + y1) / 2, text, color=DIM, fontsize=7,
            ha="left" if side > 0 else "right", va="center")


def dim_h(ax, x0, x1, y, text):
    ax.annotate("", (x0, y), (x1, y), arrowprops=dict(arrowstyle="<->", color=DIM, lw=0.8))
    ax.text((x0 + x1) / 2, y + 1.0, text, color=DIM, fontsize=7, ha="center", va="bottom")


def saddle(ax, xc, w):
    """Rounded saddle cover on a leg top, w wide (mm)."""
    h = z(EL_TOP) - z(EL_LEG_TOP)
    ax.add_patch(FancyBboxPatch((xc - w / 2, z(EL_LEG_TOP)), w, h * 0.6,
                                boxstyle=f"round,pad=0,rounding_size={min(w, h) * 0.45}",
                                fc=STEEL, ec=INK, lw=0.8))
    ax.add_patch(Rectangle((xc - w * 0.25, z(EL_LEG_TOP) + h * 0.6), w * 0.5, h * 0.4,
                           fc=STEEL, ec=INK, lw=0.8))


def leg(ax, xc, along=False):
    """One leg as stacked tiers; along=True draws its side (along the bridge) face."""
    for el0, el1, across, length in TIERS:
        w = (length if along else across) * CELL * S
        ax.add_patch(Rectangle((xc - w / 2, z(el0)), w, z(el1) - z(el0), fc=STEEL, ec=INK, lw=0.8))
        # outer cell lines: the vertical fluting of the stepped faces
        for k in (1, 2):
            for sgn in (-1, 1):
                x = xc + sgn * (w / 2 - k * CELL * S * 0.5)
                ax.plot([x, x], [z(el0), z(el1)], color=INK, lw=0.25, alpha=0.6)


def strut(ax, x0, x1, el0, el1, fluted=True):
    ax.add_patch(Rectangle((x0, z(el0)), x1 - x0, z(el1) - z(el0), fc=STEEL, ec=INK, lw=0.8))
    if fluted:
        n = max(3, int((x1 - x0) / (CELL * S * 2)))
        for i in range(1, n):
            x = x0 + (x1 - x0) * i / n
            ax.plot([x, x], [z(el0), z(el1)], color=INK, lw=0.3, alpha=0.6)


def tier_width(el, along=False):
    for el0, el1, across, length in TIERS:
        if el0 <= el <= el1:
            return (length if along else across) * CELL * S
    return TIERS[-1][3 if along else 2] * CELL * S


def pier(ax, xc, w):
    ax.add_patch(Rectangle((xc - w / 2, z(0) - 4), w, z(EL_PIER) - z(0) + 4, fc="#bbb", ec=INK, lw=0.8))


def water(ax, x0, x1):
    ax.add_patch(Rectangle((x0, z(0) - 6), x1 - x0, 6, fc=WATER, ec="none", zorder=0))
    ax.plot([x0, x1], [z(0), z(0)], color="#5dade2", lw=0.8)


def tower_front():
    fig, ax = plt.subplots(figsize=(7, 11))
    half = SPACING * S / 2
    water(ax, -half - 25, half + 25)
    pier(ax, 0, 2 * half + 12 * CELL * S)
    # below-road X-bracing: two panels between the bottom, middle and road struts
    for (a0, a1), (b0, b1) in ((BOTTOM_STRUT, MID_STRUT), (MID_STRUT, ROAD_STRUT)):
        xl = -half + tier_width(a1) / 2
        xr = half - tier_width(a1) / 2
        for p, q in (((xl, z(a1)), (xr, z(b0))), ((xr, z(a1)), (xl, z(b0)))):
            ax.plot([p[0], q[0]], [p[1], q[1]], color=STEEL, lw=3.5, solid_capstyle="butt")
            ax.plot([p[0], q[0]], [p[1], q[1]], color=INK, lw=0.4)
    for el0, el1 in (BOTTOM_STRUT, MID_STRUT, ROAD_STRUT):
        w = tier_width(el1)
        strut(ax, -half + w / 2, half - w / 2, el0, el1, fluted=False)
    # portal struts, with stepped corbels under each end
    for el0, el1 in STRUTS:
        w = tier_width(el0 - 1)
        x0, x1 = -half + w / 2, half - w / 2
        strut(ax, x0, x1, el0, el1)
        for sgn, xe in ((1, x0), (-1, x1)):
            for k, d in enumerate((0.8, 0.5, 0.25)):
                h = (k + 1) * 1.2 * CELL * S
                ax.add_patch(Rectangle((xe if sgn > 0 else xe - d * CELL * S * 2, z(el0) - h),
                                       d * CELL * S * 2, h, fc=STEEL, ec=INK, lw=0.4))
    for xc in (-half, half):
        leg(ax, xc)
        saddle(ax, xc, tier_width(EL_LEG_TOP))
        ax.add_patch(plt.Circle((xc, z(EL_TOP) - CABLE_D * S), CABLE_D * S * 1.2, fc=INK))
    # deck section, seen end on: it stops at the road strut and rests on it
    ax.add_patch(Rectangle((-half, z(EL_ROAD_TOWER - TRUSS_D)), 2 * half, TRUSS_D * S,
                           fc="none", ec=GHOST, lw=1, ls="--"))
    ax.text(-half - 9, z(EL_ROAD_TOWER - TRUSS_D / 2), "deck, end on\n(rests on the\nroad strut)",
            color=GHOST, fontsize=6, ha="right", va="center")
    dim_h(ax, -half, half, z(EL_TOP) + 6, f"road_width {SPACING * S:.1f} mm (legs and cables this far apart)")
    dim_v(ax, half + 14, z(EL_PIER), z(EL_TOP), f"tower_height {TOWER_HEIGHT:.0f} mm")
    dim_v(ax, half + 6, z(EL_PIER), z(EL_ROAD_TOWER), f"road {z(EL_ROAD_TOWER):.1f}")
    for el0, el1 in STRUTS:
        ax.text(-half - 9, z((el0 + el1) / 2), f"{z(el0):.0f}–{z(el1):.0f}", fontsize=6,
                color=DIM, ha="right", va="center")
    ax.text(-half - 9, z(EL_TOP) + 1, "struts (mm\nabove pier)", fontsize=6, color=DIM, ha="right")
    w0, w1 = TIERS[0][2] * CELL * S, TIERS[-1][2] * CELL * S
    ax.text(0, z(0) - 9, f"leg {w0:.1f} mm wide at the base, {w1:.1f} at the top",
            fontsize=7, color=DIM, ha="center")
    ax.set_title("1. One tower, looking along the road", fontsize=11)
    ax.set_aspect("equal")
    ax.set_xlim(-half - 30, half + 40)
    ax.set_ylim(z(0) - 12, z(EL_TOP) + 12)
    ax.axis("off")
    fig.savefig(OUT / "1-tower-front.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def cable_main(x):
    """Main-span cable height (ft) at x ft from the span centre: a parabola."""
    a = (EL_TOP - EL_CABLE_LOW) / (MAIN_SPAN / 2) ** 2
    return EL_CABLE_LOW + a * x * x


def road(x):
    """Road crown (ft) at x ft from the main-span centre (vertical curve)."""
    a = (EL_ROAD_MID - EL_ROAD_TOWER) / (MAIN_SPAN / 2) ** 2
    return EL_ROAD_MID - a * x * x


def tower_side():
    fig, ax = plt.subplots(figsize=(8, 10))
    reach = 330.0                                    # ft of deck shown on each side
    water(ax, -reach * S, reach * S)
    pier(ax, 0, 22 * CELL * S)
    # deck trusses, hangers and cables on both sides (side span to the left)
    xs = np.linspace(0, reach, 60)
    side_slope = (EL_TOP - 250) / SIDE_SPAN          # side cable, near straight
    for sgn in (-1, 1):
        x_ft = sgn * xs
        top = [road(MAIN_SPAN / 2 - x) if sgn > 0 else EL_ROAD_TOWER - 0.002 * x for x in xs]
        cab = [cable_main(MAIN_SPAN / 2 - x) if sgn > 0 else EL_TOP - side_slope * x for x in xs]
        ax.fill_between(x_ft * S, [z(t - TRUSS_D) for t in top], [z(t) for t in top],
                        fc="#ddd", ec=INK, lw=0.6)
        ax.plot(x_ft * S, [z(c) for c in cab], color=INK, lw=CABLE_D * S * 3)
        for xh in np.arange(HANGER_PITCH, reach, HANGER_PITCH):
            t = road(MAIN_SPAN / 2 - xh) if sgn > 0 else EL_ROAD_TOWER - 0.002 * xh
            c = cable_main(MAIN_SPAN / 2 - xh) if sgn > 0 else EL_TOP - side_slope * xh
            ax.plot([sgn * xh * S] * 2, [z(t), z(c)], color=INK, lw=0.4)
    leg(ax, 0, along=True)                           # struts sit behind it, between the legs
    saddle(ax, 0, tier_width(EL_LEG_TOP, along=True))
    dim_v(ax, -reach * S - 2, z(EL_PIER), z(EL_TOP), f"{TOWER_HEIGHT:.0f} mm", side=-1)
    dim_h(ax, 4 * HANGER_PITCH * S, 5 * HANGER_PITCH * S, z(EL_ROAD_TOWER) + 6, f"hangers {HANGER_PITCH * S:.1f} mm apart")
    d0, d1 = TIERS[0][3] * CELL * S, TIERS[-1][3] * CELL * S
    ax.text(0, z(0) - 10, f"leg {d0:.1f} mm deep at the base, {d1:.1f} at the top",
            fontsize=7, color=DIM, ha="center")
    ax.text(reach * S * 0.6, z(EL_ROAD_TOWER) + 3, "main span →", fontsize=8, color=DIM)
    ax.text(-reach * S * 0.6, z(EL_ROAD_TOWER) + 3, "← side span", fontsize=8, color=DIM, ha="right")
    ax.text(reach * S * 0.6, z(EL_ROAD_TOWER - TRUSS_D) - 4, f"deck truss {TRUSS_D * S:.1f} mm deep",
            fontsize=7, color=DIM)
    ax.set_title("2. The same tower from the side, with deck and cables", fontsize=11)
    ax.set_aspect("equal")
    ax.set_xlim(-reach * S - 12, reach * S + 4)
    ax.set_ylim(z(0) - 14, z(EL_TOP) + 8)
    ax.axis("off")
    fig.savefig(OUT / "2-tower-side.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


def whole_bridge():
    fig, ax = plt.subplots(figsize=(16, 4.2))
    L = MAIN_SPAN / 2 + SIDE_SPAN
    water(ax, -L * S - 20, L * S + 20)
    xs = np.linspace(-MAIN_SPAN / 2, MAIN_SPAN / 2, 200)
    ax.plot(xs * S, [z(cable_main(x)) for x in xs], color=INK, lw=1)
    ax.plot(xs * S, [z(road(x)) for x in xs], color=INK, lw=1.4)
    ax.fill_between(xs * S, [z(road(x) - TRUSS_D) for x in xs], [z(road(x)) for x in xs], fc="#ddd")
    for x in np.arange(-MAIN_SPAN / 2 + HANGER_PITCH, MAIN_SPAN / 2, HANGER_PITCH):
        ax.plot([x * S] * 2, [z(road(x)), z(cable_main(x))], color=INK, lw=0.25)
    for sgn in (-1, 1):
        xt = sgn * MAIN_SPAN / 2
        xa = sgn * L
        # side span: deck and cable down to the anchor block
        ax.plot([xt * S, xa * S], [z(EL_TOP), z(250)], color=INK, lw=1)
        ax.fill_between([xt * S, xa * S], [z(EL_ROAD_TOWER - TRUSS_D)] * 2, [z(EL_ROAD_TOWER), z(218)], fc="#ddd")
        ax.plot([xt * S, xa * S], [z(EL_ROAD_TOWER), z(218)], color=INK, lw=1.4)
        ax.add_patch(Rectangle((xa * S - (12 if sgn > 0 else 0), z(0)), 12, z(260) - z(0), fc="#bbb", ec=INK))
        pier(ax, xt * S, 22 * CELL * S)
        w = tier_width(EL_PIER, along=True)
        ax.add_patch(Polygon([(xt * S - w / 2, z(EL_PIER)), (xt * S + w / 2, z(EL_PIER)),
                              (xt * S + tier_width(EL_LEG_TOP, True) / 2, z(EL_TOP)),
                              (xt * S - tier_width(EL_LEG_TOP, True) / 2, z(EL_TOP))],
                             fc=STEEL, ec=INK, lw=0.8))
    dim_h(ax, -MAIN_SPAN / 2 * S, MAIN_SPAN / 2 * S, z(EL_TOP) + 6, f"main span {MAIN_SPAN * S:.0f} mm")
    dim_h(ax, -L * S, -MAIN_SPAN / 2 * S, z(EL_TOP) + 6, f"side span {SIDE_SPAN * S:.0f} mm")
    dim_h(ax, MAIN_SPAN / 2 * S, L * S, z(EL_TOP) + 6, f"side span {SIDE_SPAN * S:.0f} mm")
    dim_v(ax, 0, z(EL_CABLE_LOW), z(EL_TOP), f"sag {(EL_TOP - EL_CABLE_LOW) * S:.0f} mm")
    ax.text(0, z(0) - 5, f"suspended length {2 * L * S:.0f} mm, towers {TOWER_HEIGHT:.0f} mm "
            f"(1 : {304.8 / S:.0f})", fontsize=8, color=DIM, ha="center", va="top")
    ax.set_title("3. The whole bridge, side view", fontsize=11)
    ax.set_aspect("equal")
    ax.set_xlim(-L * S - 25, L * S + 25)
    ax.set_ylim(z(0) - 14, z(EL_TOP) + 14)
    ax.axis("off")
    fig.savefig(OUT / "3-whole-bridge.png", dpi=170, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    tower_front()
    tower_side()
    whole_bridge()
    print("wrote", OUT)
