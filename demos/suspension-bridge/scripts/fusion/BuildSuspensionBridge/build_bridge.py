# Builds the suspension bridge through the shared cad_apprentice library, so running it again
# updates the design and keeps what it didn't make. Plan, sources and parameters: ../../../README.md.
# How to write steps, and how to read a failed run: cad-apprentice/fusion/lib/README.md.
# MODE comes from the entry file. 'saved' updates the newest saved design in place and saves a new
# version of it: the normal round. 'check' does the same plus a rerun that should change nothing and
# the parameter test. 'new' builds in a new tab and saves it as a new design; only when an update in
# place can't work (fusion/rules.md rule 4). 'night' builds in a new tab like 'new', then does the
# rerun and the parameter test, but never saves.
# The parameter test runs across RANGES, quick stages first (lib README "The parameter test").
# 'check:width,height' tries only those parameters, 'check:extremes' only the all-low and all-high
# sets, 'check:random=50' 50 random sets. 'clean' wipes the saved design's whole timeline,
# builds it all again and saves a new version.
# The API works in centimetres. Sizes in expressions are in mm.
# Model frame: X across the road, centred on the bridge. Y along the bridge. Z up, with the pier top
# at Z = 0. The first tower stands on Y = 0, the second on Y = main_span_length. Every component is
# built in place, so no occurrence is moved.

import math, os, traceback
import adsk.core, adsk.fusion
import cad_apprentice
from cad_apprentice import tag, tagged, thin
from cad_apprentice.helpers import (p3, box, report_sketch, sketch_tools, to_sk, axis, projected, rectangle_n, along, keep_along,
                                   flat_face, face_edges, main_body, loose_pieces, every_profile, camera, planes_off,
                                   hide_sketches, saved_design, wipe, sketch_pictures, report)

MODE, ONLY, TEST = cad_apprentice.split_mode(MODE)

LOG = os.path.join(OUT_DIR, 'BuildSuspensionBridge.log')
SAVED_DOC = 'Suspension bridge'
# The original file, with all the rounds' versions. A second file of the same name was made by mistake.
SAVED_ID = 'urn:adsk.wipprod:dm.lineage:fd_BWNLYRB6MEn2GgdLr6Q'
SAVE_NOTE = 'Script update.'
TOWER = 'Tower'
LEG = 'Leg'
PIER = 'Pier'
DECK = 'Main span deck'
DECK_SECTIONS = tuple('%s %d' % (DECK, k) for k in range(1, 5))
SIDE_DECK = 'Side span deck'
SIDE_DECK_FAR = SIDE_DECK + ' (far end)'
ANCHOR = 'Anchor block'
ANCHOR_FAR = ANCHOR + ' (far end)'
CABLES = 'Main cables (display only)'
CABLE_MAIN = 'Main cable (main span)'
CABLE_SIDE = 'Main cable (side span)'
CABLE_SIDE_FAR = 'Main cable (far side span)'

# Marks a parameter people tune. Favorites are plain values, never formulas (fusion/rules.md rule 9).
FAV = True
# The side-span deck along the bridge: tower 1's leg face to the anchor block's inner face.
SIDE_RUN = '(side_span_length - anchor_block_length - tower_leg_tier_2_along_length / 2)'
# One foot of the real bridge, at model size. The real tower is 702 ft from the pier top (el. 44)
# to the top (el. 746), README "Heights and spans".
F = 'real_bridge_foot_model_length'
CELL = 'tower_leg_cell_size'
# A height above the first portal strut's bottom: real feet above it (strut 1 bottom is at 332 ft,
# the leg top at 683 ft), scaled to the room the clearance leaves.
UPPER = 'tower_portal_strut_1_bottom_height + %d * (tower_leg_top_height - tower_portal_strut_1_bottom_height) / 351'

PARAMS = [
    ('tower_height', '150 mm', 'mm', 'tower height from the pier top to the top of the cable saddle; every height and the leg size follow from it', FAV),
    ('road_width', '19.2 mm', 'mm', 'road deck width; the two tower legs and the two main cables are this far apart, centre to centre', FAV),
    # 897.4 mm on the real bridge's proportions (4200 ft at a 150 mm tower); 897 keeps it on the slider's grid.
    ('main_span_length', '897 mm', 'mm', 'distance between the two towers, centre to centre; the side spans and the road arc follow from it', FAV),
    # 27.3 mm on the real bridge's proportions at a 150 mm tower. Evgeny wants room for a toy train
    # here, on a shorter bridge too (2026-11-16).
    ('road_clearance', '27.3 mm', 'mm', 'free height above the road inside each tower, up to the first strut: room for a train. The struts above it squeeze or stretch to fit', FAV),
    # 0.0449 on the real bridge (9 cells of 3.5 ft on 702 ft). A higher share on a lower tower makes a
    # lower but bulkier bridge (Evgeny, 2026-11-16).
    ('leg_thickness_share', '0.045', '', 'tower leg width at its base, as a share of the tower height: higher for a bulkier tower. Capped so the legs leave the road free', FAV),
    # Scale. Heights below are real elevations less the pier top (el. 44 ft), README tables.
    (F, 'tower_height / 702', 'mm', 'one foot of the real bridge at model size: 702 ft of real tower'),
    # The cap: a road narrower than 1.4 leg widths leaves no room between the legs (rule found in the
    # range tests: road at least tower_height / 16 with legs tower_height / 22 wide).
    ('tower_leg_base_width', 'min(leg_thickness_share * tower_height; road_width / 1.4)', 'mm', 'leg width across the road at its base; every leg, strut and pier size along the bridge follows from it'),
    (CELL, 'tower_leg_base_width / 9', 'mm', 'one steel cell of the legs: the real legs are 9 cells of 3 ft 6 in across at the base'),
    # Struts, bottom and top, above the pier top: real elevation less 44 ft. README "Strut heights".
    # Strut along length and the bracing bar end height are design choices.
    ('tower_pier_strut_top_height', '16 * %s' % F, 'mm', 'bottom strut on the pier: top'),
    ('tower_brace_middle_strut_bottom_height', '88 * %s' % F, 'mm', 'strut across the middle of the bracing: bottom'),
    ('tower_brace_middle_strut_top_height', '100 * %s' % F, 'mm', 'strut across the middle of the bracing: top'),
    ('tower_road_strut_bottom_height', '166 * %s' % F, 'mm', 'strut under the road: bottom'),
    ('tower_road_strut_top_height', '181 * %s' % F, 'mm', 'strut under the road: top; the legs step in here'),
    # Above the road: the first strut sits road_clearance over the road, and everything from it to the
    # leg top keeps the real bridge's spacing, squeezed or stretched to fit (UPPER). The clearance is
    # capped at 0.6 of the room, so a typed value can't squeeze the struts above to nothing.
    ('tower_leg_top_height', '683 * %s' % F, 'mm', 'top of the legs and of the top strut, under the saddle'),
    ('deck_road_at_tower_height', '204.08 * %s' % F, 'mm', 'road top at the towers'),
    ('tower_portal_strut_1_bottom_height', 'deck_road_at_tower_height + min(road_clearance; 0.6 * (tower_leg_top_height - deck_road_at_tower_height))', 'mm', 'first portal strut above the road: bottom'),
    ('tower_portal_strut_1_top_height', UPPER % 32, 'mm', 'first portal strut: top; the legs step in here'),
    ('tower_portal_strut_2_bottom_height', UPPER % 112, 'mm', 'second portal strut: bottom'),
    ('tower_portal_strut_2_top_height', UPPER % 146, 'mm', 'second portal strut: top; the legs step in here'),
    ('tower_portal_strut_3_bottom_height', UPPER % 224, 'mm', 'third portal strut: bottom'),
    ('tower_portal_strut_3_top_height', UPPER % 256, 'mm', 'third portal strut: top; the legs step in here'),
    ('tower_top_strut_bottom_height', UPPER % 330, 'mm', 'top strut: bottom'),
    ('tower_portal_strut_height', 'tower_portal_strut_1_top_height - tower_portal_strut_1_bottom_height', 'mm', 'portal strut height; the strut face details are shares of it'),
    # Leg sizes, in cells: 9 x 15 at the base, 3 x 7 at the top (STR). The steps between are design choices.
    ('tower_leg_tier_1_across_width', '9 * %s' % CELL, 'mm', 'leg across the road, pier to road strut'),
    ('tower_leg_tier_2_across_width', '7.5 * %s' % CELL, 'mm', 'leg across the road, road strut to portal strut 1'),
    ('tower_leg_tier_3_across_width', '6 * %s' % CELL, 'mm', 'leg across the road, portal strut 1 to 2'),
    ('tower_leg_tier_4_across_width', '4.5 * %s' % CELL, 'mm', 'leg across the road, portal strut 2 to 3'),
    ('tower_leg_tier_5_across_width', '3 * %s' % CELL, 'mm', 'leg across the road, portal strut 3 to the top'),
    ('tower_leg_tier_1_along_length', '15 * %s' % CELL, 'mm', 'leg along the bridge, pier to road strut'),
    ('tower_leg_tier_2_along_length', '13 * %s' % CELL, 'mm', 'leg along the bridge, road strut to portal strut 1; the decks end on its faces'),
    ('tower_leg_tier_3_along_length', '11 * %s' % CELL, 'mm', 'leg along the bridge, portal strut 1 to 2'),
    ('tower_leg_tier_4_along_length', '9 * %s' % CELL, 'mm', 'leg along the bridge, portal strut 2 to 3'),
    ('tower_leg_tier_5_along_length', '7 * %s' % CELL, 'mm', 'leg along the bridge, portal strut 3 to the top'),
    ('tower_strut_along_length', '5 * %s' % CELL, 'mm', 'struts and bracing bars, along the bridge'),
    ('tower_brace_bar_end_height', '3 * %s' % CELL, 'mm', 'bracing bar end, measured up the leg'),
    # Each leg tier is a stepped cross in plan: bars one cell narrower across for each step out along.
    # At the base 15 x 5, 9 x 7 and 4 x 9 cells (Plate VI); the same rule up the leg is a design choice.
    ('tower_leg_cross_three_bars_middle_bar_length_share', '0.6', '', 'stepped-cross leg, 3 bars: middle bar length along the bridge, as a share of the tier length (Plate VI: 9 of 15 cells), rounded to half a cell'),
    ('tower_leg_cross_three_bars_widest_bar_length_share', '0.27', '', 'stepped-cross leg, 3 bars: widest bar length along the bridge, as a share of the tier length (Plate VI: 4 of 15 cells), rounded to half a cell'),
    ('tower_leg_cross_two_bars_widest_bar_length_share', '0.5', '', 'stepped-cross leg, 2 bars: widest bar length along the bridge, as a share of the tier length, rounded to half a cell; my choice'),
    # Portal strut faces: plain ledges top and bottom, sawtooth flutes in the upper band, a recessed
    # panel below (HAER photo 12). Flute spacing from the 1:400 model; the other sizes are design choices.
    # Each detail is a share of the strut height, so it keeps its look at any tower size (Evgeny,
    # 2026-11-16). The shares give the sizes the design had in mm at a 150 mm tower.
    ('tower_portal_strut_flute_spacing_share', '0.19', '', 'portal strut flutes: spacing along the strut, as a share of the strut height (1:400 model)'),
    # At least three flutes fit between the legs under the lowest strut, so the row's start dimension
    # never shrinks to 0 when the road clamps the legs. A distance through 0 can come back on the other
    # side, and the row then runs off the strut (a tall tower on a narrow road).
    ('tower_portal_strut_flute_spacing', 'min(tower_portal_strut_flute_spacing_share * tower_portal_strut_height; (road_width - tower_leg_tier_2_across_width) / 3.2)', 'mm', 'portal strut flutes: spacing along the strut'),
    ('tower_portal_strut_flute_depth_share', '0.31', '', 'portal strut flutes: how deep each sawtooth cuts into the face, as a share of the flute spacing; keeps the sawtooth angle'),
    ('tower_portal_strut_flute_depth', 'tower_portal_strut_flute_depth_share * tower_portal_strut_flute_spacing', 'mm', 'portal strut flutes: how deep each sawtooth cuts into the face'),
    ('tower_portal_strut_ledge_height_share', '0.09', '', 'portal strut face: plain ledge along its top and its bottom, as a share of the strut height'),
    ('tower_portal_strut_ledge_height', 'tower_portal_strut_ledge_height_share * tower_portal_strut_height', 'mm', 'portal strut face: plain ledge along its top and its bottom'),
    ('tower_portal_strut_fluted_share', '0.65', '', 'portal strut face: share of the face between the ledges that is fluted, from the top (HAER photo 12)'),
    ('tower_portal_strut_panel_side_border_width_share', '0.07', '', 'portal strut recessed panel: plain border at each leg, as a share of the strut height'),
    ('tower_portal_strut_panel_side_border_width', 'tower_portal_strut_panel_side_border_width_share * tower_portal_strut_height', 'mm', 'portal strut recessed panel: plain border at each leg'),
    ('tower_portal_strut_panel_top_bottom_border_height_share', '0.045', '', 'portal strut recessed panel: plain border above and below it, as a share of the strut height'),
    ('tower_portal_strut_panel_top_bottom_border_height', 'tower_portal_strut_panel_top_bottom_border_height_share * tower_portal_strut_height', 'mm', 'portal strut recessed panel: plain border above and below it'),
    ('tower_portal_strut_panel_depth', 'tower_portal_strut_flute_depth', 'mm', 'portal strut recessed panel: how deep it sits in the face'),
    ('tower_portal_strut_end_bracket_step_height_share', '0.09', '', 'stepped end bracket (corbel) under each portal strut end: height of each step, as a share of the strut height'),
    ('tower_portal_strut_end_bracket_step_height', 'tower_portal_strut_end_bracket_step_height_share * tower_portal_strut_height', 'mm', 'stepped end bracket under each portal strut end: height of each step'),
    ('tower_portal_strut_end_bracket_step_out_length_share', '0.67', '', 'stepped end bracket: how far each of its 3 steps sticks out past the one below, as a share of the step height; keeps the step shape'),
    # Never more than a sixth of the free gap between the legs under the lowest portal strut, so the two
    # brackets of one strut never meet when the road clamps the legs (a tall tower on a narrow road).
    ('tower_portal_strut_end_bracket_step_out_length', 'min(tower_portal_strut_end_bracket_step_out_length_share * tower_portal_strut_end_bracket_step_height; (road_width - tower_leg_tier_2_across_width) / 12)', 'mm', 'stepped end bracket: how far each of its 3 steps sticks out past the one below'),
    # Balcony on each leg's outer face at road level, with a 45-degree underside (STR: 10 ft out).
    ('tower_balcony_out_length', '10 * %s' % F, 'mm', 'balcony on the leg outer face at road level: how far it sticks out'),
    ('tower_balcony_edge_height_share', '0.28', '', 'balcony: height of its upright outer edge, above the 45-degree underside, as a share of how far the balcony sticks out'),
    ('tower_balcony_edge_height', 'tower_balcony_edge_height_share * tower_balcony_out_length', 'mm', 'balcony: height of its upright outer edge, above the 45-degree underside'),
    # Saddle: a rounded cover on the leg top and a small block on it (Plate IX; sizes are design choices).
    # In cells, like the leg top it sits on, so it stays as wide as the leg when the road clamps the leg.
    ('tower_saddle_cover_height', '3.25 * %s' % CELL, 'mm', 'saddle cover on the leg top'),
    ('tower_saddle_cover_round_radius', '1.28 * %s' % CELL, 'mm', 'round on the saddle cover top edges; under half the top tier width (3 cells), so the round fits'),
    ('tower_saddle_block_across_width', 'tower_leg_tier_5_across_width / 2', 'mm', 'block on the saddle cover, across the road'),
    ('tower_saddle_block_along_length', 'tower_leg_tier_5_along_length / 2', 'mm', 'block on the saddle cover, along the bridge'),
    # Pier under each tower (the real ones are much bigger; this is a plinth).
    ('tower_pier_height', '44 * %s' % F, 'mm', 'pier under each tower: water to the pier top'),
    ('tower_pier_across_width', 'road_width + 12 * %s' % CELL, 'mm', 'pier across the road'),
    ('tower_pier_along_length', '22 * %s' % CELL, 'mm', 'pier along the bridge'),
    # Side spans: 1125.41 ft to the main span's 4200 ft on the real bridge, README "Heights and spans".
    ('side_span_share', '0.268', '', 'side span, from a tower to the outer end of its anchor block, as a share of the main span'),
    ('side_span_length', 'side_span_share * main_span_length', 'mm', 'tower centre to the outer end of the anchor block'),
    # Deck: README "Heights and spans" and "Cables, hangers, deck". The road at the anchor is a design choice.
    ('deck_road_at_main_span_middle_height', '222.7 * %s' % F, 'mm', 'road top at mid-span'),
    ('deck_side_span_road_at_anchor_block_height', '174 * %s' % F, 'mm', 'side-span road top at the anchor block'),
    ('deck_truss_depth', '25 * %s' % F, 'mm', 'deck depth: stiffening truss, 25 ft'),
    # Deck details, sketch 5. A truss vertical at every floor beam, 25 ft apart (STR); sidewalks 10 ft (GGB).
    # The other sizes are design choices, each a share of a deck size, so they keep their look at any
    # tower size (Evgeny, 2026-11-16). The shares give the sizes the design had in mm at a 150 mm tower.
    # Slab, floor rib and bottom bar add up to at most 0.8 of the truss depth, which leaves the truss holes room.
    ('deck_truss_vertical_spacing', '25 * %s' % F, 'mm', 'deck truss: a vertical every 25 ft (STR: floor beams every 25 ft)'),
    ('deck_truss_bottom_bar_height_share', '0.15', '', 'deck truss: bottom bar (bottom chord) height, as a share of the truss depth'),
    ('deck_truss_bottom_bar_height', 'deck_truss_bottom_bar_height_share * deck_truss_depth', 'mm', 'deck truss: bottom bar (bottom chord) height'),
    ('deck_truss_vertical_and_diagonal_width_share', '0.11', '', 'deck truss: width of each vertical and diagonal, as a share of the spacing between verticals'),
    ('deck_truss_vertical_and_diagonal_width', 'deck_truss_vertical_and_diagonal_width_share * deck_truss_vertical_spacing', 'mm', 'deck truss: width of each vertical and diagonal'),
    ('deck_truss_side_wall_thickness_share', '0.15', '', 'deck truss: side wall thickness across the road, as a share of the truss depth'),
    ('deck_truss_side_wall_thickness', 'deck_truss_side_wall_thickness_share * deck_truss_depth', 'mm', 'deck truss: side wall thickness, across the road'),
    ('deck_slab_thickness_share', '0.19', '', 'deck slab under the road, as a share of the truss depth'),
    ('deck_slab_thickness', 'deck_slab_thickness_share * deck_truss_depth', 'mm', 'deck slab under the road; also the truss top chord'),
    ('deck_floor_rib_height_share', '0.28', '', 'floor rib under the slab at every panel point: depth, as a share of the truss depth'),
    ('deck_floor_rib_height', 'deck_floor_rib_height_share * deck_truss_depth', 'mm', 'floor rib under the slab at every panel point: depth'),
    ('deck_floor_rib_along_length_share', '1', '', 'floor rib: thickness along the bridge, as a share of a truss vertical\'s width'),
    ('deck_floor_rib_along_length', 'deck_floor_rib_along_length_share * deck_truss_vertical_and_diagonal_width', 'mm', 'floor rib: thickness along the bridge'),
    # The curb's top share stays under the lip's lowest, so the sidewalk never rises above the railing lip.
    ('deck_railing_lip_height_share', '0.8', '', 'side wall top above the road (the railing lip), as a share of the slab thickness. Capped so the lip stays under the main cable'),
    ('deck_sidewalk_curb_height_share', '0.3', '', 'sidewalk top above the road, as a share of the slab thickness'),
    ('deck_sidewalk_curb_height', 'deck_sidewalk_curb_height_share * deck_slab_thickness', 'mm', 'sidewalk top above the road'),
    ('deck_sidewalk_width', '10 * %s' % F, 'mm', 'sidewalk width, 10 ft (GGB)'),
    ('deck_main_span_road_arc_radius', '((main_span_length - tower_leg_tier_2_along_length)^2 / 4 + (deck_road_at_main_span_middle_height - deck_road_at_tower_height)^2) / (2 * (deck_road_at_main_span_middle_height - deck_road_at_tower_height))',
     'mm', 'main span road arc radius, from the road heights at the towers and at mid-span'),
    # Anchor blocks and cables. Cable diameter and low point from the README; anchor sizes and the cable's anchor height are design choices.
    # Capped at a quarter of the side span, so a short span keeps some deck between tower and anchor.
    ('anchor_block_length_share', '0.73', '', 'anchor block along the bridge, as a share of the pier\'s length along the bridge'),
    ('anchor_block_length', 'min(anchor_block_length_share * tower_pier_along_length; side_span_length / 4)', 'mm', 'anchor block along the bridge'),
    ('anchor_block_top_height', '216 * %s' % F, 'mm', 'anchor block top'),
    ('main_cable_at_main_span_middle_height', '232 * %s' % F, 'mm', 'main cable centre at mid-span'),
    ('main_cable_at_anchor_block_height', '206 * %s' % F, 'mm', 'main cable centre where it enters the anchor block'),
    ('main_cable_diameter', '36.375 / 12 * %s' % F, 'mm', 'main cable diameter, 36 3/8 in on the real bridge'),
    # Side span truss: the 25 ft verticals stretched a little so whole two-panel units fill the side span,
    # tower to anchor block, with no plain stretch left at either end.
    ('deck_side_span_truss_vertical_spacing', '%s / (4 * floor(%s / (4 * deck_truss_vertical_spacing)) + 2)' % (SIDE_RUN, SIDE_RUN), 'mm',
     'side span truss: a vertical about every 25 ft, stretched so whole panels fill the span'),
    # Hangers 50 ft apart, at every second truss vertical (README "Cables, hangers, deck"). The real
    # 2-11/16 in ropes would be 0.05 mm at this size, too thin to see, so the hanger and band sizes are design choices.
    ('hanger_diameter_share', '0.46', '', 'hanger (vertical cable) thickness, as a share of the main cable diameter; display only'),
    ('hanger_diameter', 'hanger_diameter_share * main_cable_diameter', 'mm', 'hanger (vertical cable) thickness; display only'),
    ('cable_band_length', '2 * main_cable_diameter', 'mm', 'band clamping a hanger to the main cable: length along the cable'),
    ('cable_band_thickness', '1.4 * main_cable_diameter', 'mm', 'cable band thickness, around the main cable'),
    # The railing lip comes after the cable sizes it uses. Capped at 0.6 of the room under the cable bands at
    # mid-span: a taller lip cut the hanger web in two there, and only one half of the main span kept its hangers.
    ('deck_railing_lip_height', 'min(deck_railing_lip_height_share * deck_slab_thickness; 0.6 * (main_cable_at_main_span_middle_height - cable_band_thickness / 2 - deck_road_at_main_span_middle_height))',
     'mm', 'side wall top above the road: the railing lip'),
]

# Ranges for the parameter test and the slicer's sliders: name -> (low, high, step), for the person
# to review (fusion/rules.md rule 19). Every other parameter is a formula. Each range is sized so its
# ends work alone and with every other range at the same end. tower_height's ends come from test runs;
# the other limits are worked out from the design's sizes, and the parameter test checks them.
# - tower_height starts at 133 mm, the lowest value tested to work, and goes up to 781 mm: a 100 mm
#   road at the default road-to-tower ratio, 19.2 to 150. road_width goes from 16 mm to 100 mm
#   (Evgeny, 2026-11-16).
# - Three clamps in the formulas, not in the ranges: the legs are never wider than road_width / 1.4,
#   which leaves room between them; road_clearance never takes more than 0.6 of the height from
#   the road to the leg top, which leaves room for the struts above it; and the railing lip never takes
#   more than 0.6 of the room under the cable bands at mid-span, which leaves the middle hangers room.
# - Details are shares of a parent size (rule 9). Their ranges keep each detail fitting its parent:
#   - the portal strut panel sits under the flutes, between the ledges: with the fluted share, ledges
#     and borders all at the top end it keeps 0.05 of the strut height;
#   - the 3 end bracket steps stick out at most 0.36 of the strut height each side, which leaves the
#     strut a panel between the legs at the widest strut (781 mm tower, 100 mm road);
#   - slab, floor rib and bottom bar add up to at most 0.8 of the truss depth, which leaves the truss
#     holes room; a truss diagonal over 0.22 of the spacing closes them;
#   - the curb's top share stays under the railing lip's lowest, so the sidewalk never rises above the
#     lip; a hanger stays thinner than the main cable.
# - Shares can make a part thinner than the nozzle lays one line on a small bridge. That's allowed: the
#   build and the test log those parts as THIN, and nothing fails (rule 9).
RANGES = {
    'tower_height': ('133 mm', '781 mm', '1 mm'),
    'road_width': ('16 mm', '100 mm', '0.2 mm'),
    'main_span_length': ('300 mm', '1800 mm', '1 mm'),
    'road_clearance': ('10 mm', '150 mm', '0.1 mm'),
    'leg_thickness_share': ('0.03', '0.085', '0.005'),
    'side_span_share': ('0.2', '0.4', '0.001'),
    'tower_leg_cross_three_bars_middle_bar_length_share': ('0.4', '0.8', '0.05'),
    'tower_leg_cross_three_bars_widest_bar_length_share': ('0.15', '0.4', '0.01'),
    'tower_leg_cross_two_bars_widest_bar_length_share': ('0.3', '0.8', '0.05'),
    'tower_portal_strut_flute_spacing_share': ('0.09', '0.44', '0.01'),
    'tower_portal_strut_flute_depth_share': ('0.1', '0.6', '0.01'),
    'tower_portal_strut_ledge_height_share': ('0.03', '0.15', '0.005'),
    'tower_portal_strut_fluted_share': ('0.3', '0.75', '0.05'),
    'tower_portal_strut_panel_side_border_width_share': ('0.03', '0.2', '0.005'),
    'tower_portal_strut_panel_top_bottom_border_height_share': ('0.015', '0.06', '0.005'),
    'tower_portal_strut_end_bracket_step_height_share': ('0.03', '0.15', '0.005'),
    'tower_portal_strut_end_bracket_step_out_length_share': ('0.2', '0.8', '0.01'),
    'tower_balcony_edge_height_share': ('0.1', '0.7', '0.01'),
    'deck_truss_bottom_bar_height_share': ('0.08', '0.2', '0.01'),
    'deck_truss_vertical_and_diagonal_width_share': ('0.06', '0.22', '0.01'),
    'deck_truss_side_wall_thickness_share': ('0.08', '0.37', '0.01'),
    'deck_slab_thickness_share': ('0.1', '0.25', '0.01'),
    'deck_floor_rib_height_share': ('0.1', '0.35', '0.01'),
    'deck_floor_rib_along_length_share': ('0.5', '2.5', '0.1'),
    'deck_railing_lip_height_share': ('0.4', '2', '0.05'),
    'deck_sidewalk_curb_height_share': ('0.1', '0.35', '0.05'),
    'anchor_block_length_share': ('0.37', '1.8', '0.01'),
    'hanger_diameter_share': ('0.31', '0.77', '0.01'),
}
assert set(RANGES) <= {p[0] for p in PARAMS}, 'RANGES names a parameter PARAMS lacks'

# A slicer's Customize panel lists the favorites in the order the design made them.
FAV_ORDER = ['tower_height', 'road_width', 'main_span_length', 'road_clearance', 'leg_thickness_share']
assert sorted(FAV_ORDER) == sorted(n for n, *rest in PARAMS if rest[3:]), 'FAV_ORDER must list every favorite once'
OLD_NAMES = {}
# Parameters renamed for plainer names: new name -> old name. b.param renames them in place, so
# their values carry over. Keep this until the saved design has been run once with the new names.
WAS = {
    'tower_pier_strut_top_height': 'tower_bottom_strut_top_height',
    'tower_leg_cross_three_bars_middle_bar_length_share': 'tower_leg_cross_middle_bar_length_share',
    'tower_leg_cross_three_bars_widest_bar_length_share': 'tower_leg_cross_short_bar_length_share',
    'tower_leg_cross_two_bars_widest_bar_length_share': 'tower_leg_cross_two_bars_short_bar_length_share',
    'tower_portal_strut_flute_spacing': 'tower_strut_flute_pitch',
    'tower_portal_strut_flute_depth': 'tower_strut_flute_depth',
    'tower_portal_strut_ledge_height': 'tower_strut_ledge_height',
    'tower_portal_strut_fluted_share': 'tower_strut_fluted_share',
    'tower_portal_strut_panel_side_border_width': 'tower_strut_panel_side_border_width',
    'tower_portal_strut_panel_top_bottom_border_height': 'tower_strut_panel_top_bottom_border_height',
    'tower_portal_strut_panel_depth': 'tower_strut_panel_depth',
    'tower_portal_strut_end_bracket_step_out_length': 'tower_strut_corbel_step_out_length',
    'tower_portal_strut_end_bracket_step_height': 'tower_strut_corbel_step_height',
    'deck_road_at_main_span_middle_height': 'deck_road_at_middle_height',
    'deck_side_span_road_at_anchor_block_height': 'deck_side_road_at_anchor_height',
    'deck_truss_vertical_spacing': 'deck_truss_panel_length',
    'deck_truss_bottom_bar_height': 'deck_truss_bottom_chord_height',
    'deck_truss_vertical_and_diagonal_width': 'deck_truss_member_width',
    'deck_truss_side_wall_thickness': 'deck_truss_wall_thickness',
    'deck_floor_rib_height': 'deck_rib_depth',
    'deck_floor_rib_along_length': 'deck_rib_thickness',
    'deck_sidewalk_curb_height': 'deck_curb_height',
    'deck_main_span_road_arc_radius': 'deck_road_arc_radius',
    'main_cable_at_main_span_middle_height': 'main_cable_low_height',
    'main_cable_at_anchor_block_height': 'main_cable_anchor_height',
}

ACROSS = ['tower_leg_tier_%d_across_width' % k for k in range(1, 6)]
ALONG = ['tower_leg_tier_%d_along_length' % k for k in range(1, 6)]
TIER_TOPS = ['tower_road_strut_top_height', 'tower_portal_strut_1_top_height', 'tower_portal_strut_2_top_height',
             'tower_portal_strut_3_top_height', 'tower_leg_top_height']
X, Y, Z = (1, 0, 0), (0, 1, 0), (0, 0, 1)


def from_part(s, sketch, name, occ):
    # A tagged line from another component's sketch, as seen in the bridge. Construction only.
    return projected(s, tagged(sketch, name).createForAssemblyContext(occ))


def sizes(um):
    # Starting sizes in cm. Only starting points: the constraints and dimensions define the shape.
    # evaluateExpression answers in cm whatever unit it is given.
    v = lambda x: um.evaluateExpression(x, 'mm')
    return {k: v(k) for k, *_ in PARAMS if _[1] == 'mm'}




# ---------- Tower ----------

# One leg's outline, seen across d: five tiers, each narrower than the one below, stepping in at the
# tops in TIER_TOPS. Points a0..a9 run up the -d side, b0..b9 up the +d side; a(2k), a(2k+1) are the
# bottom and top of tier k+1. centre is a line along Z the leg is symmetric about, base the line its
# foot stands on. Returns the points and the lines a(i)a(i+1), b(i)b(i+1) and the top line.
# cap: each step in is a 45-degree slope, not a flat ledge (Plate VIII).
def draw_leg_outline(s, d, c, centre, base, widths, g, attempt, size, cap=False):
    gc, dims = s.geometricConstraints, s.sketchDimensions
    at = lambda u, z: s.sketchPoints.add(to_sk(s, d[0] * u, d[1] * u, z))
    w, t = [g[n] for n in widths], [g[n] for n in TIER_TOPS]
    rise = [(w[k] - w[k + 1]) / 2 if cap else 0.0 for k in range(4)]
    bottoms = [0.0] + [t[k] + rise[k] for k in range(4)]
    a, b = [], []
    for k in range(5):
        for side, pts in ((-1, a), (1, b)):
            pts += [at(c + side * w[k] / 2, bottoms[k]), at(c + side * w[k] / 2, t[k])]
    lines = s.sketchCurves.sketchLines
    la = [lines.addByTwoPoints(a[i], a[i + 1]) for i in range(9)]
    lb = [lines.addByTwoPoints(b[i], b[i + 1]) for i in range(9)]
    top = lines.addByTwoPoints(a[9], b[9])
    lines.addByTwoPoints(b[0], a[0])
    for i in range(9):
        k = i // 2
        if cap and i % 2:
            r = '(%s - %s) / 2' % (widths[k], widths[k + 1])
            for side, p in ((-1, a), (1, b)):
                u = c + side * (w[k] / 2 + 0.2)
                size('tier %d cap rise (%s side)' % (k + 2, '-+'[side > 0]), lambda: dims.addDistanceDimension(p[i], p[i + 1], along(s, Z), to_sk(s, d[0] * u, d[1] * u, t[k] + rise[k] / 2)), r)
            continue
        way = Z if i % 2 == 0 else d
        attempt('leg -side line %d along its axis' % i, lambda: keep_along(s, la[i], way))
        attempt('leg +side line %d along its axis' % i, lambda: keep_along(s, lb[i], way))
    attempt('leg foot on the base (-side)', lambda: gc.addCoincident(a[0], base))
    attempt('leg foot on the base (+side)', lambda: gc.addCoincident(b[0], base))
    left = c - w[0] / 2
    for k in range(5):
        i = 2 * k + 1
        attempt('tier %d top corners symmetric' % (k + 1), lambda: gc.addSymmetry(a[i], b[i], centre))
        size('tier %d width' % (k + 1), lambda: dims.addDistanceDimension(a[i], b[i], along(s, d), to_sk(s, d[0] * c, d[1] * c, t[k] + 0.15)), widths[k])
        u = left - 0.4 - 0.25 * k
        size('tier %d top height' % (k + 1), lambda: dims.addDistanceDimension(a[0], a[i], along(s, Z), to_sk(s, d[0] * u, d[1] * u, t[k] / 2)), TIER_TOPS[k])
    return a, b, la, lb, top


# The leg seen along the road (XZ), on the -X side. Its centre line is road_width / 2 from the middle.
# The steps in have 45-degree caps on this view only.
def draw_tower_front(s, comp, um, out):
    g = sizes(um)
    W = g['road_width']
    refused, attempt, size, gc, dims = sketch_tools(s)
    x_ax = axis(s, comp.xConstructionAxis)
    m0, m1 = (s.sketchPoints.add(to_sk(s, -W / 2, 0, z)) for z in (0.0, g['tower_leg_top_height']))
    mid = s.sketchCurves.sketchLines.addByTwoPoints(m0, m1)
    mid.isConstruction = True
    a, b, la, lb, top = draw_leg_outline(s, X, -W / 2, mid, x_ax, ACROSS, g, attempt, size, cap=True)
    attempt('leg centre line starts on the pier top', lambda: gc.addCoincident(m0, x_ax))
    attempt('leg centre line upright', lambda: keep_along(s, mid, Z))
    attempt('leg centre line ends on the leg top', lambda: gc.addCoincident(m1, top))
    size('leg centre from the bridge centre', lambda: dims.addDistanceDimension(s.originPoint, m0, along(s, X), to_sk(s, -W / 4, 0, -0.3)), 'road_width / 2')
    tag(a[9], 'leg_top_outer')
    tag(b[9], 'leg_top_inner')
    tag(mid, 'leg_centre')
    tag(m0, 'leg_foot_centre')
    report_sketch(s, refused, out)
    if s.profiles.count != 1:
        raise Exception('expected one closed outline for the leg front, got %d' % s.profiles.count)


# The leg seen from the side (YZ), centred on Y = 0. Cuts the steps along the bridge into the leg.
def draw_tower_side(s, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    y_ax, z_ax = axis(s, comp.yConstructionAxis), axis(s, comp.zConstructionAxis)
    a, b, la, lb, top = draw_leg_outline(s, Y, 0.0, z_ax, y_ax, ALONG, g, attempt, size)
    # The decks end on these faces.
    tag(la[2], 'tier_2_face_minus_y')
    tag(lb[2], 'tier_2_face_plus_y')
    report_sketch(s, refused, out)
    if s.profiles.count != 1:
        raise Exception('expected one closed outline for the leg side, got %d' % s.profiles.count)


# The saddle cover on the leg top, as wide as the top tier, centred on the leg.
def draw_saddle_cover(s, front, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    centre = projected(s, tagged(front, 'leg_centre'))
    c, w = -g['road_width'] / 2, g['tower_leg_tier_5_across_width'] / 2
    z0 = g['tower_leg_top_height']
    z1 = z0 + g['tower_saddle_cover_height']
    v = [s.sketchPoints.add(to_sk(s, x, 0, z)) for x, z in ((c - w, z0), (c + w, z0), (c + w, z1), (c - w, z1))]
    lines = rectangle_n(s, v)
    attempt('cover bottom corners symmetric', lambda: gc.addSymmetry(v[0], v[1], centre))
    attempt('cover top corners symmetric', lambda: gc.addSymmetry(v[3], v[2], centre))
    attempt('cover side upright', lambda: keep_along(s, lines[1], Z))
    size('cover width', lambda: dims.addDistanceDimension(v[0], v[1], along(s, X), to_sk(s, c, 0, z0 - 0.2)), 'tower_leg_tier_5_across_width')
    size('cover bottom height', lambda: dims.addDistanceDimension(s.originPoint, v[0], along(s, Z), to_sk(s, c - 0.6, 0, z0 / 2)), 'tower_leg_top_height')
    size('cover top height', lambda: dims.addDistanceDimension(s.originPoint, v[3], along(s, Z), to_sk(s, c - 0.8, 0, z1 / 2)), 'tower_leg_top_height + tower_saddle_cover_height')
    report_sketch(s, refused, out)


# The block on the saddle cover, centred on the leg, up to the tower top.
def draw_saddle_block(s, front, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    centre = projected(s, tagged(front, 'leg_centre'))
    c, w = -g['road_width'] / 2, g['tower_saddle_block_across_width'] / 2
    z0, z1 = g['tower_leg_top_height'] + g['tower_saddle_cover_height'] / 2, g['tower_height']
    v = [s.sketchPoints.add(to_sk(s, x, 0, z)) for x, z in ((c - w, z0), (c + w, z0), (c + w, z1), (c - w, z1))]
    lines = rectangle_n(s, v)
    attempt('block bottom corners symmetric', lambda: gc.addSymmetry(v[0], v[1], centre))
    attempt('block top corners symmetric', lambda: gc.addSymmetry(v[3], v[2], centre))
    attempt('block side upright', lambda: keep_along(s, lines[1], Z))
    size('block width', lambda: dims.addDistanceDimension(v[0], v[1], along(s, X), to_sk(s, c, 0, z0 - 0.2)), 'tower_saddle_block_across_width')
    size('block bottom height', lambda: dims.addDistanceDimension(s.originPoint, v[0], along(s, Z), to_sk(s, c - 0.6, 0, z0 / 2)), 'tower_leg_top_height + tower_saddle_cover_height / 2')
    size('block top height', lambda: dims.addDistanceDimension(s.originPoint, v[3], along(s, Z), to_sk(s, c - 0.8, 0, z1 / 2)), 'tower_height')
    report_sketch(s, refused, out)


# A strut from leg centre to leg centre, centred on the Z axis, from bottom to top (expressions). No
# bottom means it stands on the pier top. Its corners are tagged prefix + '_bottom_left' and so on.
def centred_rect(s, z_ax, x_ax, prefix, bottom, top, g, attempt, size):
    gc, dims = s.geometricConstraints, s.sketchDimensions
    W = g['road_width']
    zb, zt = g[bottom] if bottom else 0.0, g[top]
    r = [s.sketchPoints.add(to_sk(s, x, 0, z)) for x, z in ((-W / 2, zb), (W / 2, zb), (W / 2, zt), (-W / 2, zt))]
    lines = rectangle_n(s, r)
    attempt(prefix + ' bottom corners symmetric', lambda: gc.addSymmetry(r[0], r[1], z_ax))
    attempt(prefix + ' top corners symmetric', lambda: gc.addSymmetry(r[3], r[2], z_ax))
    attempt(prefix + ' side upright', lambda: keep_along(s, lines[1], Z))
    size(prefix + ' width', lambda: dims.addDistanceDimension(r[0], r[1], along(s, X), to_sk(s, 0, 0, zt + 0.15)), 'road_width')
    if bottom:
        size(prefix + ' bottom height', lambda: dims.addDistanceDimension(s.originPoint, r[0], along(s, Z), to_sk(s, W / 2 + 0.6, 0, zb / 2)), bottom)
    else:
        attempt(prefix + ' on the pier top', lambda: gc.addCoincident(r[0], x_ax))
    size(prefix + ' top height', lambda: dims.addDistanceDimension(s.originPoint, r[3], along(s, Z), to_sk(s, W / 2 + 0.9, 0, zt / 2)), top)
    for q, n in zip(r, ('_bottom_left', '_bottom_right', '_top_right', '_top_left')):
        tag(q, prefix + n)


BRACE_STRUTS = [('brace_bottom', None, 'tower_pier_strut_top_height'),
                ('brace_middle', 'tower_brace_middle_strut_bottom_height', 'tower_brace_middle_strut_top_height'),
                ('brace_road', 'tower_road_strut_bottom_height', 'tower_road_strut_top_height')]
PORTAL_STRUTS = [('portal_1', 'tower_portal_strut_1_bottom_height', 'tower_portal_strut_1_top_height'),
                 ('portal_2', 'tower_portal_strut_2_bottom_height', 'tower_portal_strut_2_top_height'),
                 ('portal_3', 'tower_portal_strut_3_bottom_height', 'tower_portal_strut_3_top_height'),
                 ('portal_top', 'tower_top_strut_bottom_height', 'tower_leg_top_height')]
# The road through the tower, between the legs: on the road strut, up to the road top, as long along the
# bridge as the legs so the decks butt onto it. The sidewalks go round the legs on the balconies.
ROAD_THROUGH = [('road_through', 'tower_road_strut_top_height', 'deck_road_at_tower_height')]


def draw_struts(s, comp, um, out, struts):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    x_ax, z_ax = axis(s, comp.xConstructionAxis), axis(s, comp.zConstructionAxis)
    for prefix, bottom, top in struts:
        centred_rect(s, z_ax, x_ax, prefix, bottom, top, g, attempt, size)
    report_sketch(s, refused, out)
    if s.profiles.count != len(struts):
        raise Exception('expected %d struts in %s, got %d profiles' % (len(struts), s.name, s.profiles.count))


# Below the road, two panels of crossed bars: bottom strut to middle strut, middle strut to road strut.
# Each bar runs from a lower strut's top corner to the upper strut's bottom corner on the other leg,
# and is tower_brace_bar_end_height tall where it meets each leg.
def draw_brace_bars(s, struts, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    e = g['tower_brace_bar_end_height']
    for lower, upper in (('brace_bottom', 'brace_middle'), ('brace_middle', 'brace_road')):
        for start, end in (('_top_left', '_bottom_right'), ('_top_right', '_bottom_left')):
            label = '%s%s to %s%s bar' % (lower, start, upper, end)
            p1, p3_ = projected(s, tagged(struts, lower + start)), projected(s, tagged(struts, upper + end))
            g1, g3 = s.sketchToModelSpace(p1.geometry), s.sketchToModelSpace(p3_.geometry)
            p2, p4 = s.sketchPoints.add(to_sk(s, g1.x, 0, g1.z + e)), s.sketchPoints.add(to_sk(s, g3.x, 0, g3.z - e))
            lower_end, _, upper_end, _ = rectangle_n(s, [p1, p2, p3_, p4])
            attempt(label + ' lower end upright', lambda: keep_along(s, lower_end, Z))
            attempt(label + ' upper end upright', lambda: keep_along(s, upper_end, Z))
            size(label + ' lower end', lambda: dims.addDistanceDimension(p1, p2, along(s, Z), to_sk(s, g1.x * 1.1, 0, g1.z + e / 2)), 'tower_brace_bar_end_height')
            size(label + ' upper end', lambda: dims.addDistanceDimension(p4, p3_, along(s, Z), to_sk(s, g3.x * 1.1, 0, g3.z - e / 2)), 'tower_brace_bar_end_height')
    report_sketch(s, refused, out)


# A rectangle in a plan sketch, centred on the point centre, across (X) by along (Y): expressions.
def plan_rect(s, centre, across, along_, um, attempt, size, label):
    gc, dims = s.geometricConstraints, s.sketchDimensions
    c = s.sketchToModelSpace(centre.geometry)
    w, l = (um.evaluateExpression(e, 'mm') / 2 for e in (across, along_))
    r = [s.sketchPoints.add(to_sk(s, c.x + i * w, c.y + j * l)) for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
    lines = rectangle_n(s, r)
    for i, line in enumerate(lines):
        attempt('%s side %d straight' % (label, i), lambda: keep_along(s, line, X if i % 2 == 0 else Y))
    diag = s.sketchCurves.sketchLines.addByTwoPoints(r[0], r[2])
    diag.isConstruction = True
    attempt(label + ' centred', lambda: gc.addMidPoint(centre, diag))
    size(label + ' across', lambda: dims.addDistanceDimension(r[0], r[1], along(s, X), to_sk(s, c.x, c.y - l - 0.1)), across)
    size(label + ' along', lambda: dims.addDistanceDimension(r[1], r[2], along(s, Y), to_sk(s, c.x + w + 0.1, c.y)), along_)


# Leg tier k's stepped cross in plan, as (across, along) expressions per bar, narrowest first. The bar
# count comes from the tier's size in cells when the sketch is drawn (sketch_details.py leg_plan):
# 3 bars if the narrowest is still a cell wide, 2 if it is 1.5 cells, else a plain rectangle.
def leg_cross_bars(k, g):
    A, L = ACROSS[k], ALONG[k]
    n = g[A] / g[CELL]
    rounded = lambda share: 'floor(%s * %s / (%s / 2) + 0.5) * %s / 2' % (share, L, CELL, CELL)
    if n - 4 >= 1 - 1e-6:
        return [('%s - 4 * %s' % (A, CELL), L), ('%s - 2 * %s' % (A, CELL), rounded('tower_leg_cross_three_bars_middle_bar_length_share')),
                (A, rounded('tower_leg_cross_three_bars_widest_bar_length_share'))]
    if n - 2 >= 1.5 - 1e-6:
        return [('%s - 2 * %s' % (A, CELL), L), (A, rounded('tower_leg_cross_two_bars_widest_bar_length_share'))]
    return []


# The corners cut off leg tier k to leave the stepped cross: a box a cell bigger all round, and the
# bars. The ring between them is the cut.
def draw_leg_cross(s, front, k, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    centre = projected(s, tagged(front, 'leg_foot_centre'))
    plan_rect(s, centre, '%s + 2 * %s' % (ACROSS[k], CELL), '%s + 2 * %s' % (ALONG[k], CELL), um, attempt, size, 'box')
    for j, (a, l) in enumerate(leg_cross_bars(k, g)):
        plan_rect(s, centre, a, l, um, attempt, size, 'bar %d' % (j + 1))
    report_sketch(s, refused, out)


def cross_ring(s):
    rings = [p for p in s.profiles if p.profileLoops.count > 1]
    if len(rings) != 1:
        raise Exception('expected one ring around the leg cross in %s, got %d' % (s.name, len(rings)))
    return rings[0]


# Portal strut i's leg tier: the struts sit on tiers 2, 3 and 4.
DETAILED_STRUTS = [(prefix, bottom, top, ACROSS[i + 1]) for i, (prefix, bottom, top) in enumerate(PORTAL_STRUTS[:3])]
FLUTED_BAND = '(%s - %s - 2 * tower_portal_strut_ledge_height) * tower_portal_strut_fluted_share'


# Under each end of each portal strut, a corbel of 3 steps out from the leg's inner face, the widest on
# top. Drawn from the leg centre line so it joins the leg. The +X leg's corbels mirror the -X ones.
def draw_corbels(s, front, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    centre = projected(s, tagged(front, 'leg_centre'))
    z_ax = axis(s, comp.zConstructionAxis)
    xc = -g['road_width'] / 2
    o, h = g['tower_portal_strut_end_bracket_step_out_length'], g['tower_portal_strut_end_bracket_step_height']
    for prefix, bottom, _, A in DETAILED_STRUTS:
        zb, xf = g[bottom], xc + g[A] / 2
        pts = [(xc, zb), (xf + 3 * o, zb), (xf + 3 * o, zb - h), (xf + 2 * o, zb - h), (xf + 2 * o, zb - 2 * h),
               (xf + o, zb - 2 * h), (xf + o, zb - 3 * h), (xc, zb - 3 * h)]
        p = [s.sketchPoints.add(to_sk(s, x, 0, z)) for x, z in pts]
        lines = rectangle_n(s, p)
        label = prefix + ' corbel'
        attempt(label + ' top on the leg centre', lambda: gc.addCoincident(p[0], centre))
        attempt(label + ' bottom on the leg centre', lambda: gc.addCoincident(p[7], centre))
        for j in range(7):
            attempt('%s line %d straight' % (label, j), lambda: keep_along(s, lines[j], X if j % 2 == 0 else Z))
        size(label + ' top height', lambda: dims.addDistanceDimension(s.originPoint, p[0], along(s, Z), to_sk(s, xc - 0.3, 0, zb / 2)), bottom)
        size(label + ' top step', lambda: dims.addDistanceDimension(p[0], p[1], along(s, X), to_sk(s, xf, 0, zb + 0.1)), '%s / 2 + 3 * tower_portal_strut_end_bracket_step_out_length' % A)
        for j in range(1, 6):
            way, expr = (Z, 'tower_portal_strut_end_bracket_step_height') if j % 2 else (X, 'tower_portal_strut_end_bracket_step_out_length')
            q = s.sketchToModelSpace(p[j].geometry)
            size('%s step %d' % (label, j), lambda: dims.addDistanceDimension(p[j], p[j + 1], along(s, way), to_sk(s, q.x + 0.15, 0, q.z - 0.15)), expr)
        m = [s.sketchPoints.add(to_sk(s, -x, 0, z)) for x, z in pts]
        rectangle_n(s, m)
        for j in range(8):
            attempt('%s point %d mirrored on the +X leg' % (label, j), lambda: gc.addSymmetry(p[j], m[j], z_ax))
    report_sketch(s, refused, out)


# On each leg's outer face at road level, a balcony with an upright edge and a 45-degree underside.
# Drawn from the leg centre line so it joins the leg. The +X leg's balcony mirrors the -X one.
def draw_balconies(s, front, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    centre = projected(s, tagged(front, 'leg_centre'))
    z_ax = axis(s, comp.zConstructionAxis)
    xc, A = -g['road_width'] / 2, ACROSS[1]
    xf, out_, e, zr = xc - g[A] / 2, g['tower_balcony_out_length'], g['tower_balcony_edge_height'], g['deck_road_at_tower_height']
    pts = [(xc, zr), (xf - out_, zr), (xf - out_, zr - e), (xf, zr - e - out_), (xc, zr - e - out_)]
    p = [s.sketchPoints.add(to_sk(s, x, 0, z)) for x, z in pts]
    lines = rectangle_n(s, p)
    attempt('balcony top on the leg centre', lambda: gc.addCoincident(p[0], centre))
    attempt('balcony bottom on the leg centre', lambda: gc.addCoincident(p[4], centre))
    attempt('balcony top flat', lambda: keep_along(s, lines[0], X))
    attempt('balcony edge upright', lambda: keep_along(s, lines[1], Z))
    attempt('balcony bottom flat', lambda: keep_along(s, lines[3], X))
    size('balcony top height', lambda: dims.addDistanceDimension(s.originPoint, p[0], along(s, Z), to_sk(s, xc + 0.3, 0, zr / 2)), 'deck_road_at_tower_height')
    size('balcony top', lambda: dims.addDistanceDimension(p[0], p[1], along(s, X), to_sk(s, xf, 0, zr + 0.15)), '%s / 2 + tower_balcony_out_length' % A)
    size('balcony edge', lambda: dims.addDistanceDimension(p[1], p[2], along(s, Z), to_sk(s, xf - out_ - 0.15, 0, zr - e / 2)), 'tower_balcony_edge_height')
    size('balcony underside across', lambda: dims.addDistanceDimension(p[2], p[3], along(s, X), to_sk(s, xf - out_ / 2, 0, zr - e - out_ - 0.15)), 'tower_balcony_out_length')
    size('balcony underside down', lambda: dims.addDistanceDimension(p[2], p[3], along(s, Z), to_sk(s, xf - out_ - 0.3, 0, zr - e - out_ / 2)), 'tower_balcony_out_length')
    m = [s.sketchPoints.add(to_sk(s, -x, 0, z)) for x, z in pts]
    rectangle_n(s, m)
    for j in range(5):
        attempt('balcony point %d mirrored on the +X leg' % j, lambda: gc.addSymmetry(p[j], m[j], z_ax))
    report_sketch(s, refused, out)


# One flute of a portal strut in plan, on each face: a sawtooth tooth tower_portal_strut_flute_spacing long and
# tower_portal_strut_flute_depth deep, at the -X end of the row. A pattern repeats it along the strut.
def draw_flute(s, comp, A, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    x_ax = axis(s, comp.xConstructionAxis)
    pitch, depth, t = g['tower_portal_strut_flute_spacing'], g['tower_portal_strut_flute_depth'], g['tower_strut_along_length'] / 2
    x0 = -max(1, math.floor((g['road_width'] - g[A]) / pitch + 1e-6)) * pitch / 2
    pts = [(x0, t), (x0 + pitch, t), (x0 + pitch, t - depth)]
    p = [s.sketchPoints.add(to_sk(s, x, y)) for x, y in pts]
    face, back, _ = rectangle_n(s, p)
    attempt('flute face line along the strut', lambda: keep_along(s, face, X))
    attempt('flute back upright to the face', lambda: keep_along(s, back, Y))
    size('flute row start', lambda: dims.addDistanceDimension(s.originPoint, p[0], along(s, X), to_sk(s, x0 / 2, t + 0.3)),
         'max(1; floor((road_width - %s) / tower_portal_strut_flute_spacing)) * tower_portal_strut_flute_spacing / 2' % A)
    size('flute on the strut face', lambda: dims.addDistanceDimension(s.originPoint, p[0], along(s, Y), to_sk(s, x0 - 0.3, t / 2)), 'tower_strut_along_length / 2')
    size('flute pitch', lambda: dims.addDistanceDimension(p[0], p[1], along(s, X), to_sk(s, x0 + pitch / 2, t + 0.15)), 'tower_portal_strut_flute_spacing')
    size('flute depth', lambda: dims.addDistanceDimension(p[1], p[2], along(s, Y), to_sk(s, x0 + pitch + 0.15, t)), 'tower_portal_strut_flute_depth')
    m = [s.sketchPoints.add(to_sk(s, x, -y)) for x, y in pts]
    rectangle_n(s, m)
    for j in range(3):
        attempt('flute point %d mirrored on the -Y face' % j, lambda: gc.addSymmetry(p[j], m[j], x_ax))
    report_sketch(s, refused, out)


# The plain recessed panel on the +Y face of each portal strut, below the flutes, inside a border.
def draw_strut_panels(s, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    z_ax = axis(s, comp.zConstructionAxis)
    t = g['tower_strut_along_length'] / 2
    ledge, side, tb = g['tower_portal_strut_ledge_height'], g['tower_portal_strut_panel_side_border_width'], g['tower_portal_strut_panel_top_bottom_border_height']
    for prefix, bottom, top, A in DETAILED_STRUTS:
        band = um.evaluateExpression(FLUTED_BAND % (top, bottom), 'mm')
        w = (g['road_width'] - g[A]) / 2 - side
        z0, z1 = g[bottom] + ledge + tb, g[top] - ledge - band - tb
        r = [s.sketchPoints.add(to_sk(s, x, t, z)) for x, z in ((-w, z0), (w, z0), (w, z1), (-w, z1))]
        lines = rectangle_n(s, r)
        label = prefix + ' panel'
        attempt(label + ' bottom corners symmetric', lambda: gc.addSymmetry(r[0], r[1], z_ax))
        attempt(label + ' top corners symmetric', lambda: gc.addSymmetry(r[3], r[2], z_ax))
        attempt(label + ' side upright', lambda: keep_along(s, lines[1], Z))
        size(label + ' width', lambda: dims.addDistanceDimension(r[0], r[1], along(s, X), to_sk(s, 0, t, z0 - 0.15)),
             'road_width - %s - 2 * tower_portal_strut_panel_side_border_width' % A)
        size(label + ' bottom height', lambda: dims.addDistanceDimension(s.originPoint, r[0], along(s, Z), to_sk(s, w + 0.4, t, z0 / 2)),
             '%s + tower_portal_strut_ledge_height + tower_portal_strut_panel_top_bottom_border_height' % bottom)
        size(label + ' top height', lambda: dims.addDistanceDimension(s.originPoint, r[3], along(s, Z), to_sk(s, w + 0.7, t, z1 / 2)),
             '%s - tower_portal_strut_ledge_height - %s - tower_portal_strut_panel_top_bottom_border_height' % (top, FLUTED_BAND % (top, bottom)))
    report_sketch(s, refused, out)


# ---------- Pier ----------

def draw_pier(s, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    x_ax, y_ax = axis(s, comp.xConstructionAxis), axis(s, comp.yConstructionAxis)
    A, L = g['tower_pier_across_width'] / 2, g['tower_pier_along_length'] / 2
    r = [s.sketchPoints.add(to_sk(s, x, y, 0)) for x, y in ((-A, -L), (A, -L), (A, L), (-A, L))]
    rectangle_n(s, r)
    attempt('front corners symmetric', lambda: gc.addSymmetry(r[0], r[1], y_ax))
    attempt('back corners symmetric', lambda: gc.addSymmetry(r[3], r[2], y_ax))
    attempt('right corners symmetric', lambda: gc.addSymmetry(r[1], r[2], x_ax))
    size('pier across', lambda: dims.addDistanceDimension(r[0], r[1], along(s, X), to_sk(s, 0, -L - 0.3, 0)), 'tower_pier_across_width')
    size('pier along', lambda: dims.addDistanceDimension(r[1], r[2], along(s, Y), to_sk(s, A + 0.3, 0, 0)), 'tower_pier_along_length')
    report_sketch(s, refused, out)


# ---------- Anchor block ----------

# Seen from the side (YZ): on the floor the piers stand on, its outer face side_span_length from tower 1.
def draw_anchor(s, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    S, L, P, T = g['side_span_length'], g['anchor_block_length'], g['tower_pier_height'], g['anchor_block_top_height']
    a, b, c, d = (s.sketchPoints.add(to_sk(s, 0, y, z)) for y, z in ((-S, -P), (-S, T), (-S + L, T), (-S + L, -P)))
    outer, top, inner, bottom = rectangle_n(s, [a, b, c, d])
    attempt('outer face upright', lambda: keep_along(s, outer, Z))
    attempt('inner face upright', lambda: keep_along(s, inner, Z))
    attempt('top flat', lambda: keep_along(s, top, Y))
    attempt('bottom flat', lambda: keep_along(s, bottom, Y))
    size('outer face from tower 1', lambda: dims.addDistanceDimension(s.originPoint, a, along(s, Y), to_sk(s, 0, -S / 2, -P - 0.4)), 'side_span_length')
    size('floor under the pier top', lambda: dims.addDistanceDimension(s.originPoint, a, along(s, Z), to_sk(s, 0, -S - 0.5, -P / 2)), 'tower_pier_height')
    size('top height', lambda: dims.addDistanceDimension(s.originPoint, b, along(s, Z), to_sk(s, 0, -S - 0.9, T / 2)), 'anchor_block_top_height')
    size('length', lambda: dims.addDistanceDimension(b, c, along(s, Y), to_sk(s, 0, -S + L / 2, T + 0.3)), 'anchor_block_length')
    tag(inner, 'anchor_inner_face')
    report_sketch(s, refused, out)


# ---------- Decks ----------

# The deck levels, top down, as (name, height from the road top, sign): the side walls' railing lip, the
# sidewalk top, the road, the slab bottom (the truss top chord) and the deck bottom. Each deck sketch
# draws one line or arc per level. The 4 bands between them, bottom up: under the slab, the slab, road
# to sidewalk top, sidewalk top to railing lip (sketch 5).
LEVELS = [('railing lip top', 'deck_railing_lip_height', 1), ('sidewalk top', 'deck_sidewalk_curb_height', 1), ('road', None, 0),
          ('slab bottom', 'deck_slab_thickness', -1), ('deck bottom', 'deck_truss_depth', -1)]


def level_heights(g):
    return [sign * g[e] if e else 0.0 for _, e, sign in LEVELS]


# The side-span deck seen from the side: a straight run from tower 1's leg face (-Y side) down to the
# anchor block's inner face, one line per level. The road line ends on both faces; the others run
# parallel to it, their ends on the two upright end lines.
def draw_side_deck(s, b, tower_side, anchor_sk, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    face = from_part(s, tower_side, 'tier_2_face_minus_y', b.known['tower'])
    inner = from_part(s, anchor_sk, 'anchor_inner_face', b.known['anchor'])
    yt, ya = -g['tower_leg_tier_2_along_length'] / 2, -g['side_span_length'] + g['anchor_block_length']
    zt, za = g['deck_road_at_tower_height'], g['deck_side_span_road_at_anchor_block_height']
    hs = level_heights(g)
    T = [s.sketchPoints.add(to_sk(s, 0, yt, zt + h)) for h in hs]
    A = [s.sketchPoints.add(to_sk(s, 0, ya, za + h)) for h in hs]
    lines = s.sketchCurves.sketchLines
    runs = [lines.addByTwoPoints(t, a) for t, a in zip(T, A)]
    tower_end, anchor_end = lines.addByTwoPoints(T[0], T[4]), lines.addByTwoPoints(A[0], A[4])
    road = runs[2]
    attempt('tower end upright', lambda: keep_along(s, tower_end, Z))
    attempt('anchor end upright', lambda: keep_along(s, anchor_end, Z))
    for i in (1, 2, 3):
        attempt('%s on the tower end' % LEVELS[i][0], lambda: gc.addCoincident(T[i], tower_end))
        attempt('%s on the anchor end' % LEVELS[i][0], lambda: gc.addCoincident(A[i], anchor_end))
    attempt('road end on the tower leg', lambda: gc.addCoincident(T[2], face))
    attempt('road end on the anchor block', lambda: gc.addCoincident(A[2], inner))
    size('road at the tower', lambda: dims.addDistanceDimension(s.originPoint, T[2], along(s, Z), to_sk(s, 0, yt + 0.5, zt / 2)), 'deck_road_at_tower_height')
    size('road at the anchor', lambda: dims.addDistanceDimension(s.originPoint, A[2], along(s, Z), to_sk(s, 0, ya + 0.5, za / 2)), 'deck_side_span_road_at_anchor_block_height')
    for i in (0, 1, 3, 4):
        name, expr, _ = LEVELS[i]
        attempt('%s parallel to the road' % name, lambda: gc.addParallel(runs[i], road))
        size('%s at the tower' % name, lambda: dims.addDistanceDimension(T[2], T[i], along(s, Z), to_sk(s, 0, yt - 0.2 - 0.15 * i, zt + hs[i] / 2)), expr)
    tag(road, 'side_road')
    tag(runs[4], 'side_bottom')
    tag(runs[0], 'side_top')
    report_sketch(s, refused, out)
    if s.profiles.count != 4:
        raise Exception('expected 4 side deck bands, got %d profiles' % s.profiles.count)


# The main-span deck seen from the side: one arc per level between the two towers' leg faces, all
# around one centre, the road highest at mid-span. An upright construction line at mid-span, tagged for
# the truss sketches, runs from the railing lip top down to the deck bottom.
def draw_main_deck(s, b, tower_side, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    face = from_part(s, tower_side, 'tier_2_face_plus_y', b.known['tower'])
    y0, M = g['tower_leg_tier_2_along_length'] / 2, g['main_span_length']
    zt, zm = g['deck_road_at_tower_height'], g['deck_road_at_main_span_middle_height']
    hs = level_heights(g)
    arcs, lines = s.sketchCurves.sketchArcs, s.sketchCurves.sketchLines
    by_y = lambda q: s.sketchToModelSpace(q.geometry).y
    arc = [arcs.addByThreePoints(to_sk(s, 0, y0, zt + h), to_sk(s, 0, M / 2, zm + h), to_sk(s, 0, M - y0, zt + h)) for h in hs]
    ends = [sorted([a.startSketchPoint, a.endSketchPoint], key=by_y) for a in arc]
    end0, end1 = lines.addByTwoPoints(ends[0][0], ends[4][0]), lines.addByTwoPoints(ends[0][1], ends[4][1])
    road = arc[2]
    p0, p1 = ends[2]
    mid = lines.addByTwoPoints(to_sk(s, 0, M / 2, zm + hs[0]), to_sk(s, 0, M / 2, zm + hs[4]))
    mid.isConstruction = True
    t, d = mid.startSketchPoint, mid.endSketchPoint
    c = s.sketchPoints.add(to_sk(s, 0, M / 2, zm))
    attempt('deck end at tower 1 upright', lambda: keep_along(s, end0, Z))
    attempt('deck end at tower 2 upright', lambda: keep_along(s, end1, Z))
    for i in (1, 2, 3):
        attempt('%s on the tower 1 end' % LEVELS[i][0], lambda: gc.addCoincident(ends[i][0], end0))
        attempt('%s on the tower 2 end' % LEVELS[i][0], lambda: gc.addCoincident(ends[i][1], end1))
    attempt('road end on tower 1', lambda: gc.addCoincident(p0, face))
    size('road at the tower', lambda: dims.addDistanceDimension(s.originPoint, p0, along(s, Z), to_sk(s, 0, y0 + 0.5, zt / 2)), 'deck_road_at_tower_height')
    for i in (0, 1, 3, 4):
        attempt('%s around the road centre' % LEVELS[i][0], lambda: gc.addConcentric(arc[i], road))
    attempt('mid-span line top on the railing lip', lambda: gc.addCoincident(t, arc[0]))
    attempt('mid-span line bottom on the deck bottom', lambda: gc.addCoincident(d, arc[4]))
    attempt('mid-span line upright', lambda: keep_along(s, mid, Z))
    attempt('mid-span road point on the mid-span line', lambda: gc.addCoincident(c, mid))
    attempt('mid-span road point on the road', lambda: gc.addCoincident(c, road))
    size('mid-span from tower 1', lambda: dims.addDistanceDimension(s.originPoint, c, along(s, Y), to_sk(s, 0, M / 4, -0.5)), 'main_span_length / 2')
    size('road at mid-span', lambda: dims.addDistanceDimension(s.originPoint, c, along(s, Z), to_sk(s, 0, M / 2 + 1, zm / 2)), 'deck_road_at_main_span_middle_height')
    attempt('road ends symmetric about mid-span', lambda: gc.addSymmetry(p0, p1, mid))
    size('railing lip at mid-span', lambda: dims.addDistanceDimension(c, t, along(s, Z), to_sk(s, 0, M / 2 + 0.3, zm + hs[0] / 2)), LEVELS[0][1])
    size('depth at mid-span', lambda: dims.addDistanceDimension(c, d, along(s, Z), to_sk(s, 0, M / 2 + 0.3, zm + hs[4] / 2)), LEVELS[4][1])
    for i in (1, 3):
        name, expr, _ = LEVELS[i]
        q = s.sketchPoints.add(to_sk(s, 0, M / 2, zm + hs[i]))
        attempt('%s point on the mid-span line' % name, lambda: gc.addCoincident(q, mid))
        attempt('%s point on its arc' % name, lambda: gc.addCoincident(q, arc[i]))
        size('%s at mid-span' % name, lambda: dims.addDistanceDimension(c, q, along(s, Z), to_sk(s, 0, M / 2 - 0.3, zm + hs[i] / 2)), expr)
    tag(mid, 'deck_mid')
    tag(arc[0], 'main_top')
    tag(c, 'deck_road_mid')
    report_sketch(s, refused, out)
    if s.profiles.count != 4:
        raise Exception('expected 4 main deck bands, got %d profiles' % s.profiles.count)


def bands(*ks):
    # The deck sketch's bands numbered ks, counted from the bottom (LEVELS).
    def pick(s):
        if s.profiles.count != 4:
            raise Exception('expected 4 deck bands in %s, got %d profiles' % (s.name, s.profiles.count))
        def z(p):
            bb = p.boundingBox
            return s.sketchToModelSpace(p3((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2)).z
        ordered = sorted(s.profiles, key=z)
        c = adsk.core.ObjectCollection.create()
        for k in ks:
            c.add(ordered[k])
        return c
    return pick


# Where a truss sketch draws its one unit, as (c, d, mid, flat): c the road top at the unit's middle,
# d the deck bottom under it, mid the upright line between them, flat(line) keeps a line along the road.
def main_frame(deck_sk):
    # At mid-span, from the deck sketch's mid-span line.
    def frame(s, attempt):
        mid = projected(s, tagged(deck_sk, 'deck_mid'))
        c = projected(s, tagged(deck_sk, 'deck_road_mid'))
        d = min((mid.startSketchPoint, mid.endSketchPoint), key=lambda q: s.sketchToModelSpace(q.geometry).z)
        return c, d, mid, lambda line: keep_along(s, line, Y)
    return frame


def side_frame(side_sk):
    # Halfway along the side span's road.
    def frame(s, attempt):
        gc = s.geometricConstraints
        road, bottom = (projected(s, tagged(side_sk, n)) for n in ('side_road', 'side_bottom'))
        a, e = (s.sketchToModelSpace(q.geometry) for q in (road.startSketchPoint, road.endSketchPoint))
        f, h = (s.sketchToModelSpace(q.geometry) for q in (bottom.startSketchPoint, bottom.endSketchPoint))
        yc, zc = (a.y + e.y) / 2, (a.z + e.z) / 2
        zd = f.z + (yc - f.y) * (h.z - f.z) / (h.y - f.y)
        c = s.sketchPoints.add(to_sk(s, 0, yc, zc))
        mid = s.sketchCurves.sketchLines.addByTwoPoints(c, to_sk(s, 0, yc, zd))
        mid.isConstruction = True
        d = mid.endSketchPoint
        attempt('unit middle halfway along the road', lambda: gc.addMidPoint(c, road))
        attempt('unit middle line upright', lambda: keep_along(s, mid, Z))
        attempt('unit middle line ends on the deck bottom', lambda: gc.addCoincident(d, bottom))
        return c, d, mid, lambda line: gc.addParallel(line, road)
    return frame


# One unit of the truss's open triangles, two panels long, centred on the frame's middle line: on each
# side a diagonal runs from the top chord at the middle down to the bottom chord a panel out, with a
# vertical at the middle and at each panel point (sketch 5). The holes are the two triangles each side
# leaves between the chords, the verticals and the diagonal. A pattern repeats the unit along the deck.
def draw_truss_unit(s, c, d, mid, flat, g, attempt, size, panel):
    gc, dims, lines = s.geometricConstraints, s.sketchDimensions, s.sketchCurves.sketchLines
    P, m = g[panel], g['deck_truss_vertical_and_diagonal_width']
    q = s.sketchToModelSpace(c.geometry)
    yc, zc, zd = q.y, q.z, s.sketchToModelSpace(d.geometry).z
    za, zb = zc - g['deck_slab_thickness'], zd + g['deck_truss_bottom_bar_height']
    pt = lambda y, z: s.sketchPoints.add(to_sk(s, 0, y, z))
    A, B = pt(yc, za), pt(yc, zb)
    attempt('top chord point on the middle line', lambda: gc.addCoincident(A, mid))
    attempt('bottom chord point on the middle line', lambda: gc.addCoincident(B, mid))
    size('top chord under the road', lambda: dims.addDistanceDimension(c, A, along(s, Z), to_sk(s, 0, yc + 0.1, (zc + za) / 2)), 'deck_slab_thickness')
    size('bottom chord height', lambda: dims.addDistanceDimension(B, d, along(s, Z), to_sk(s, 0, yc + 0.1, (zb + zd) / 2)), 'deck_truss_bottom_bar_height')
    L = math.hypot(P, za - zb)
    for side in (-1, 1):
        label = '%s side' % '-+'[side > 0]
        ty, tz = side * P / L, (zb - za) / L
        ny, nz = -tz * side, ty * side  # across the diagonal, to its upper side
        # The diagonal's edges, m / 2 above and below the line from A to D.
        at_z = lambda o, z: (yc + o * ny * m / 2 + (z - za - o * nz * m / 2) * ty / tz, z)
        at_y = lambda o, y: (y, za + o * nz * m / 2 + (y - yc - o * ny * m / 2) * tz / ty)
        D = pt(yc + side * P, zb)
        u = [pt(*xy) for xy in ((yc + side * (P - m / 2), za), at_z(1, za), at_y(1, yc + side * (P - m / 2)))]
        lo = [pt(*xy) for xy in ((yc + side * m / 2, zb), at_z(-1, zb), at_y(-1, yc + side * m / 2))]
        diag = lines.addByTwoPoints(A, D)
        diag.isConstruction = True
        chords = []
        for name, tri, chord_point in (('upper', u, A), ('lower', lo, B)):
            chord, slant, upright = rectangle_n(s, tri)
            chords.append(chord)
            attempt('%s %s hole along the deck' % (label, name), lambda: flat(chord))
            attempt('%s %s hole edge through its chord point' % (label, name), lambda: gc.addCoincident(chord_point, chord))
            attempt('%s %s hole side upright' % (label, name), lambda: keep_along(s, upright, Z))
            attempt('%s %s hole along the diagonal' % (label, name), lambda: gc.addParallel(slant, diag))
            mp = s.sketchToModelSpace(slant.startSketchPoint.geometry)
            size('%s %s hole off the diagonal' % (label, name), lambda: dims.addOffsetDimension(slant, diag, to_sk(s, 0, mp.y, mp.z)), 'deck_truss_vertical_and_diagonal_width / 2')
        attempt('%s panel point on the bottom chord' % label, lambda: gc.addCoincident(D, chords[1]))
        size('%s panel length' % label, lambda: dims.addDistanceDimension(c, D, along(s, Y), to_sk(s, 0, yc + side * P / 2, zd - 0.2)), panel)
        size('%s vertical at the panel point' % label, lambda: dims.addDistanceDimension(D, u[0], along(s, Y), to_sk(s, 0, yc + side * P, za + 0.2)), 'deck_truss_vertical_and_diagonal_width / 2')
        size('%s vertical at the middle' % label, lambda: dims.addDistanceDimension(c, lo[0], along(s, Y), to_sk(s, 0, yc + side * m, zb - 0.2)), 'deck_truss_vertical_and_diagonal_width / 2')


def draw_holes(s, frame, um, out, panel='deck_truss_vertical_spacing'):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    c, d, mid, flat = frame(s, attempt)
    draw_truss_unit(s, c, d, mid, flat, g, attempt, size, panel)
    report_sketch(s, refused, out)
    if s.profiles.count != 4:
        raise Exception('expected 4 truss holes in %s, got %d profiles' % (s.name, s.profiles.count))


# One floor rib under the slab, centred on the frame's middle line: from inside the slab down
# deck_floor_rib_height below it, deck_floor_rib_along_length along the deck. A pattern repeats it at every panel point.
def draw_rib(s, frame, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    c, d, mid, flat = frame(s, attempt)
    q = s.sketchToModelSpace(c.geometry)
    yc, zc, t = q.y, q.z, g['deck_floor_rib_along_length']
    ze, zf = zc - g['deck_slab_thickness'] / 2, zc - g['deck_slab_thickness'] - g['deck_floor_rib_height']
    pt = lambda y, z: s.sketchPoints.add(to_sk(s, 0, y, z))
    E, F = pt(yc, ze), pt(yc, zf)
    r = [pt(yc - t / 2, ze), pt(yc + t / 2, ze), pt(yc + t / 2, zf), pt(yc - t / 2, zf)]
    top, right, bottom, left = rectangle_n(s, r)
    attempt('rib top point on the middle line', lambda: gc.addCoincident(E, mid))
    attempt('rib bottom point on the middle line', lambda: gc.addCoincident(F, mid))
    size('rib top inside the slab', lambda: dims.addDistanceDimension(c, E, along(s, Z), to_sk(s, 0, yc + 0.2, (zc + ze) / 2)), 'deck_slab_thickness / 2')
    size('rib bottom', lambda: dims.addDistanceDimension(c, F, along(s, Z), to_sk(s, 0, yc + 0.3, (zc + zf) / 2)), 'deck_slab_thickness + deck_floor_rib_height')
    attempt('rib top along the deck', lambda: flat(top))
    attempt('rib bottom along the deck', lambda: flat(bottom))
    attempt('rib top through its point', lambda: gc.addCoincident(E, top))
    attempt('rib bottom through its point', lambda: gc.addCoincident(F, bottom))
    attempt('rib sides upright', lambda: keep_along(s, right, Z))
    attempt('rib other side upright', lambda: keep_along(s, left, Z))
    size('rib thickness', lambda: dims.addDistanceDimension(r[0], r[1], along(s, Y), to_sk(s, 0, yc, ze + 0.2)), 'deck_floor_rib_along_length')
    size('rib centred', lambda: dims.addDistanceDimension(c, r[0], along(s, Y), to_sk(s, 0, yc - t, zc + 0.2)), 'deck_floor_rib_along_length / 2')
    report_sketch(s, refused, out)


# ---------- Cables ----------

# One main cable seen from the side, on the -X leg's centre line: a curve from the top of tower 1 down
# to main_cable_at_main_span_middle_height at mid-span and up to the top of tower 2, and a straight run from tower 1
# down to the anchor block. The curve is a spline through five points of a parabola, the shape a real
# cable takes: the tower tops, the low point and the quarter points, a quarter of the sag above the low
# point. Not an arc: an arc deeper than half its span flips the long way round, and a tall tower set
# before a long span made one that the sketch then couldn't solve back.
def draw_cables(s, comp, um, out):
    g = sizes(um)
    refused, attempt, size, gc, dims = sketch_tools(s)
    y_ax, z_ax = axis(s, comp.yConstructionAxis), axis(s, comp.zConstructionAxis)
    xw, M, Ht, zl = -g['road_width'] / 2, g['main_span_length'], g['tower_height'], g['main_cable_at_main_span_middle_height']
    S, za = g['side_span_length'], g['main_cable_at_anchor_block_height']
    zq = zl + (Ht - zl) / 4
    P = lambda y, z: to_sk(s, xw, y, z)
    lines = s.sketchCurves.sketchLines
    fit = adsk.core.ObjectCollection.create()
    for y, z in ((0, Ht), (M / 4, zq), (M / 2, zl), (3 * M / 4, zq), (M, Ht)):
        fit.add(P(y, z))
    curve = s.sketchCurves.sketchFittedSplines.add(fit)
    p0, q0, c, q1, p1 = sorted(curve.fitPoints, key=lambda q: s.sketchToModelSpace(q.geometry).y)
    cm = lines.addByTwoPoints(c, P(M / 2, 0))
    cm.isConstruction = True
    m = cm.endSketchPoint
    side = lines.addByTwoPoints(p0, P(-S, za))
    a = side.endSketchPoint
    attempt('cable over tower 1', lambda: gc.addCoincident(p0, z_ax))
    size('cable top height', lambda: dims.addDistanceDimension(s.originPoint, p0, along(s, Z), P(-1, Ht / 2)), 'tower_height')
    attempt('mid-span line ends on the pier top level', lambda: gc.addCoincident(m, y_ax))
    attempt('mid-span line upright', lambda: keep_along(s, cm, Z))
    size('low point from tower 1', lambda: dims.addDistanceDimension(s.originPoint, c, along(s, Y), P(M / 4, -0.5)), 'main_span_length / 2')
    size('low point height', lambda: dims.addDistanceDimension(s.originPoint, c, along(s, Z), P(M / 2 + 1, zl / 2)), 'main_cable_at_main_span_middle_height')
    attempt('cable ends symmetric about mid-span', lambda: gc.addSymmetry(p0, p1, cm))
    size('quarter point from tower 1', lambda: dims.addDistanceDimension(s.originPoint, q0, along(s, Y), P(M / 8, -0.5)), 'main_span_length / 4')
    size('quarter point height', lambda: dims.addDistanceDimension(s.originPoint, q0, along(s, Z), P(M / 4 + 1, zq / 2)),
         'main_cable_at_main_span_middle_height + (tower_height - main_cable_at_main_span_middle_height) / 4')
    attempt('quarter points symmetric about mid-span', lambda: gc.addSymmetry(q0, q1, cm))
    size('anchor end from tower 1', lambda: dims.addDistanceDimension(s.originPoint, a, along(s, Y), P(-S / 2, -0.5)), 'side_span_length')
    size('anchor end height', lambda: dims.addDistanceDimension(s.originPoint, a, along(s, Z), P(-S - 0.5, za / 2)), 'main_cable_at_anchor_block_height')
    tag(curve, 'main_curve')
    tag(side, 'side_line')
    report_sketch(s, refused, out)


def along_curve(s, curve, y):
    # The point on a sketch line or arc at model y, and the curve's direction there as a unit (dy, dz)
    # with dy > 0. Starting places only: the constraints put things where they belong.
    ev = curve.geometry.evaluator
    _, t0, t1 = ev.getParameterExtents()
    at = lambda t: s.sketchToModelSpace(ev.getPointAtParameter(t)[1])
    if at(t0).y > at(t1).y:
        t0, t1 = t1, t0
    step = (t1 - t0) * 1e-4
    for _ in range(50):
        tm = (t0 + t1) / 2
        if at(tm).y < y:
            t0 = tm
        else:
            t1 = tm
    q, r = at(t0), at(t0 + step)
    dy, dz = r.y - q.y, r.z - q.z
    if dy < 0:
        dy, dz = -dy, -dz
    n = math.hypot(dy, dz)
    return q, (dy / n, dz / n)


# The hangers start as one thin web between the main cable and the deck top, in the cable plane, from
# just past the tower to just past the far end. A row of gap blocks then cuts away everything between
# hangers. The bands work the same way on a sleeve around the cable. Few constraints, so the sketch
# solves at once (a sketch with a constrained shape per hanger, 600 constraints, hung Fusion).

# ends: two (y, expr) places, y in cm, expr the distance from tower 1. One upright line at each end, from
# the deck top to the cable; the web is the region between them, the cable and the deck top.
def draw_web(s, cable, top, ends, out):
    refused, attempt, size, gc, dims = sketch_tools(s)
    lines = s.sketchCurves.sketchLines
    for k, (y, expr) in enumerate(ends):
        zc, zd = along_curve(s, cable, y)[0].z, along_curve(s, top, y)[0].z
        ln = lines.addByTwoPoints(to_sk(s, 0, y, zd), to_sk(s, 0, y, zc))
        a, e = ln.startSketchPoint, ln.endSketchPoint
        attempt('web end %d upright' % k, lambda: keep_along(s, ln, Z))
        attempt('web end %d foot on the deck' % k, lambda: gc.addCoincident(a, top))
        attempt('web end %d top on the cable' % k, lambda: gc.addCoincident(e, cable))
        size('web end %d from tower 1' % k, lambda: dims.addDistanceDimension(s.originPoint, a, along(s, Y), to_sk(s, 0, y / 2, zd - 1)), expr)
    report_sketch(s, refused, out)


def edge(s, entity):
    # A line or arc from another sketch as a real edge of this one, so it can bound a profile.
    q = s.project(entity).item(0)
    q.isConstruction = False
    return q


def biggest_profile(s):
    c = adsk.core.ObjectCollection.create()
    c.add(max(s.profiles, key=lambda p: p.areaProperties().area))
    return c


# Blocks seen from the side, from just above the floor to above the cable tops. rects: ((y1, expr1),
# (y2, expr2)) each, y in cm (its sign says which side of tower 1), expr the distance from tower 1.
def draw_blocks(s, rects, um, out):
    refused, attempt, size, gc, dims = sketch_tools(s)
    z0, z1 = '1 mm', 'tower_height + cable_band_thickness'
    zs = [um.evaluateExpression(z, 'mm') for z in (z0, z1)]
    for k, ((ya, ea), (yb, eb)) in enumerate(rects):
        r = s.sketchCurves.sketchLines.addTwoPointRectangle(to_sk(s, 0, ya, zs[0]), to_sk(s, 0, yb, zs[1]))
        for ln in r:
            # The API's rectangle comes without its square-corner constraints, so they go on here.
            a, c = (s.sketchToModelSpace(x.geometry) for x in (ln.startSketchPoint, ln.endSketchPoint))
            d = Y if abs(a.y - c.y) > abs(a.z - c.z) else Z
            attempt('block %d side' % k, lambda ln=ln, d=d: keep_along(s, ln, d))
        p, q = r.item(0).startSketchPoint, r.item(2).startSketchPoint
        pm, qm = (s.sketchToModelSpace(x.geometry) for x in (p, q))
        for pt, m in ((p, pm), (q, qm)):
            ey = ea if abs(m.y - ya) < abs(m.y - yb) else eb
            ez = z0 if abs(m.z - zs[0]) < abs(m.z - zs[1]) else z1
            size('block %d corner from tower 1' % k, lambda: dims.addDistanceDimension(s.originPoint, pt, along(s, Y), to_sk(s, 0, m.y / 2, m.z + 0.5)), ey)
            size('block %d corner height' % k, lambda: dims.addDistanceDimension(s.originPoint, pt, along(s, Z), to_sk(s, 0, m.y + 0.5, m.z / 2)), ez)
    report_sketch(s, refused, out)
    if s.profiles.count != len(rects):
        raise Exception('%s: expected %d block profiles, got %d' % (s.name, len(rects), s.profiles.count))


def hanger_layout(um, key):
    # Everything the hanger steps of one span need: where the web ends, the tooth on the middle hanger for
    # a hanger or band width, and the rows that repeat it away from tower 1 and back (each counts the tooth).
    ev = lambda e: um.evaluateExpression(e, 'mm')
    at = lambda sign, e: (sign * ev(e), e)
    if key == 'main':
        ends = [at(1, MAIN_END), at(1, 'main_span_length - %s' % MAIN_END)]
        tooth = lambda w: (at(1, 'main_span_length / 2 - %s / 2' % w), at(1, 'main_span_length / 2 + %s / 2' % w))
        rows = [('away', MAIN_HANG, '2 * %s' % P_), ('back', MAIN_HANG, '-2 * %s' % P_)]
    else:
        ends = [at(-1, SIDE_END_IN), at(-1, SIDE_END_OUT)]
        tooth = lambda w: (at(-1, '%s - %s / 2' % (SIDE_CENTRE, w)), at(-1, '%s + %s / 2' % (SIDE_CENTRE, w)))
        rows = [('away', SIDE_UNITS, '-2 * %s' % SIDE_PANEL), ('back', SIDE_UNITS, '2 * %s' % SIDE_PANEL)]
    return dict(ends=ends, tooth=tooth, rows=rows)


def one_body(b, key):
    # A joined cable must be one body: a hanger that missed the cable would stay loose and be left
    # out of the copies.
    n = b.known[key].bodies.count
    if n != 1:
        raise Exception('%s: expected 1 body after the join, found %d' % (key, n))
    return b.body(key)


# ---------- Shared steps ----------

# Through every deck wall, for the truss hole cuts.
THROUGH = 'road_width + 2 * deck_truss_side_wall_thickness'


def deck_body(b, comp, key, sk, body_name):
    # A deck from its side sketch's 4 bands (sketch 5): all 4 across the full width with the walls, the
    # inside of the truss and of the railing band cut away to leave the walls, then the road cut down
    # between the sidewalks. Returns the body, as participants.
    body = lambda: [b.body(key + '_block')]
    b.extrude(key + '_block', '%s block' % body_name, sk, New, symmetric='road_width + deck_truss_side_wall_thickness', body_name=body_name,
              profile=bands(0, 1, 2, 3))
    b.extrude(key + '_hollow', '%s inside the walls' % body_name, sk, Cut, symmetric='road_width - deck_truss_side_wall_thickness',
              participants=body, profile=bands(0, 3), uses=[key + '_block'])
    b.extrude(key + '_roadway', '%s roadway' % body_name, sk, Cut, symmetric='road_width - deck_truss_side_wall_thickness - 2 * deck_sidewalk_width',
              participants=body, profile=bands(2), uses=[key + '_hollow'])
    return body


def centre_y(x):
    return (x.boundingBox.minPoint.y + x.boundingBox.maxPoint.y) / 2


# Units along each half of a deck, each counted from the middle unit. A truss hole unit is 2 panels long,
# a rib sits at every panel point. Half the main span runs from mid-span to the tower leg face; half the
# side span from its middle to either end.
MAIN_HALF = '((main_span_length - tower_leg_tier_2_along_length) / 2)'
SIDE_HALF = '(%s / 2)' % SIDE_RUN
HOLE_UNITS = 'floor((%s / deck_truss_vertical_spacing - 1) / 2) + 1'
# The side span holds a whole odd number of units, so its middle unit plus this many each way fill it.
SIDE_UNITS = 'floor(%s / (4 * deck_truss_vertical_spacing)) + 1' % SIDE_RUN
SIDE_PANEL = 'deck_side_span_truss_vertical_spacing'
RIBS = 'floor((%s - deck_floor_rib_along_length / 2) / %s) + 1'
P_ = 'deck_truss_vertical_spacing'
# Main span: a hanger every 2 panels from mid-span both ways, while it stays half a panel off tower 1's
# leg face. MAIN_HANG counts them from mid-span to tower 1, the middle one included.
MAIN_END = '(tower_leg_tier_2_along_length / 2 + %s / 2)' % P_
MAIN_HANG = 'floor((main_span_length / 2 - %s) / (2 * %s)) + 1' % (MAIN_END, P_)
# Side span: a hanger every 2 side panels from the side span's middle both ways (SIDE_UNITS each way).
SIDE_CENTRE = '(tower_leg_tier_2_along_length / 2 + %s / 2)' % SIDE_RUN
SIDE_END_IN = '(tower_leg_tier_2_along_length / 2 + %s / 2)' % SIDE_PANEL
SIDE_END_OUT = '(tower_leg_tier_2_along_length / 2 + %s - %s / 2)' % (SIDE_RUN, SIDE_PANEL)
# The main deck's quarter cuts, at the panel point nearest the middle of each half.
QUARTER = 'main_span_length / 2 %s deck_truss_vertical_spacing * floor(%s / 2 / deck_truss_vertical_spacing + 0.5)'


New = adsk.fusion.FeatureOperations.NewBodyFeatureOperation
Join = adsk.fusion.FeatureOperations.JoinFeatureOperation
Cut = adsk.fusion.FeatureOperations.CutFeatureOperation
Intersect = adsk.fusion.FeatureOperations.IntersectFeatureOperation


def describe(b):
    out = b.log
    um = b.des.unitsManager
    um.distanceDisplayUnits = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
    # Favorites first, in FAV_ORDER. They are plain values, so nothing they use comes later.
    favs = {p[0]: p for p in PARAMS if p[4:]}
    for name, expr, unit, comment, *fav in [favs[n] for n in FAV_ORDER] + [p for p in PARAMS if p[0] not in favs]:
        r = RANGES.get(name)
        b.param(name, expr, unit, comment, favorite=bool(fav), was=WAS.get(name),
                range=r and r[:2], step=r and r[2])

    # One tower, printed. The bridge preview puts a copy at the far end.
    with b.component('tower', TOWER) as comp:
        with b.group('Tower · legs'):
            # The -X leg: its outline seen along the road, then the steps along the bridge cut in from the side.
            front = b.sketch('tower_front_sketch', 'Tower front', lambda: comp.xZConstructionPlane, lambda s: draw_tower_front(s, comp, um, out),
                             spec=(sizes, draw_leg_outline, draw_tower_front))
            b.extrude('leg_extrude', 'Leg extrude', front, New, symmetric='tower_leg_tier_1_along_length', body_name=LEG)
            tower_side = b.sketch('tower_side_sketch', 'Tower side', lambda: comp.yZConstructionPlane, lambda s: draw_tower_side(s, comp, um, out),
                                  spec=(sizes, draw_leg_outline, draw_tower_side))
            b.extrude('leg_side_steps', 'Leg side steps', tower_side, Intersect, symmetric='2 * (road_width + tower_leg_tier_1_across_width)',
                      participants=lambda: [b.body('leg_extrude')], uses=['leg_extrude'])
        with b.group('Tower · saddle'):
            cover_sk = b.sketch('saddle_cover_sketch', 'Saddle cover', lambda: comp.xZConstructionPlane, lambda s: draw_saddle_cover(s, front, um, out),
                                spec=(sizes, draw_saddle_cover), uses=['tower_front_sketch'])
            b.extrude('saddle_cover', 'Saddle cover extrude', cover_sk, New, symmetric='tower_leg_tier_5_along_length', body_name='Saddle cover')
            b.fillet('saddle_cover_round', 'Saddle cover round',
                     lambda: [(face_edges(flat_face(b.body('saddle_cover'), Z, um.evaluateExpression('tower_leg_top_height + tower_saddle_cover_height', 'cm')), True),
                               'tower_saddle_cover_round_radius')], uses=['saddle_cover'])
            block_sk = b.sketch('saddle_block_sketch', 'Saddle block', lambda: comp.xZConstructionPlane, lambda s: draw_saddle_block(s, front, um, out),
                                spec=(sizes, draw_saddle_block), uses=['tower_front_sketch'])
            b.extrude('saddle_block', 'Saddle block extrude', block_sk, New, symmetric='tower_saddle_block_along_length', body_name='Saddle block')
        with b.group('Tower · leg cross'):
            # Each tier's corners cut away to leave the stepped cross, from where the tier's own straight sides
            # start (above the 45-degree cap) up to its top.
            cross_keys = []
            for k in range(4):
                start = '0 mm' if k == 0 else '%s + (%s - %s) / 2' % (TIER_TOPS[k - 1], ACROSS[k - 1], ACROSS[k])
                if k == 0:
                    plane, plane_keys = (lambda: comp.xYConstructionPlane), []
                else:
                    pl = b.offset_plane('leg_cross_%d_plane' % k, 'Leg cross tier %d floor' % (k + 1), comp.xYConstructionPlane, start)
                    plane, plane_keys = (lambda pl=pl: pl), ['leg_cross_%d_plane' % k]
                cross_sk = b.sketch('leg_cross_%d_sketch' % k, 'Leg cross tier %d' % (k + 1), plane,
                                    lambda s, k=k: draw_leg_cross(s, front, k, um, out),
                                    spec=(sizes, plan_rect, leg_cross_bars, draw_leg_cross, k), uses=['tower_front_sketch'] + plane_keys)
                b.extrude('leg_cross_%d' % k, 'Leg cross tier %d cut' % (k + 1), cross_sk, Cut, distance='%s - (%s)' % (TIER_TOPS[k], start),
                          participants=lambda: [b.body('leg_extrude')], profile=cross_ring, uses=['leg_side_steps'])
                cross_keys.append('leg_cross_%d' % k)
        with b.group('Tower · second leg'):
            b.rect_pattern('second_leg', 'Second leg', lambda: [b.body('leg_extrude'), b.body('saddle_cover'), b.body('saddle_block')],
                           comp.xConstructionAxis, '2', 'road_width', comp.yConstructionAxis, '1', 'road_width',
                           uses=['leg_side_steps', 'saddle_cover_round', 'saddle_block'] + cross_keys)
        with b.group('Tower · struts'):
            brace_sk = b.sketch('brace_strut_sketch', 'Brace struts', lambda: comp.xZConstructionPlane,
                                lambda s: draw_struts(s, comp, um, out, BRACE_STRUTS), spec=(sizes, centred_rect, draw_struts, BRACE_STRUTS))
            b.extrude('brace_struts', 'Brace struts extrude', brace_sk, New, symmetric='tower_strut_along_length', body_name='Brace strut', profile=every_profile)
            portal_sk = b.sketch('portal_strut_sketch', 'Portal struts', lambda: comp.xZConstructionPlane,
                                 lambda s: draw_struts(s, comp, um, out, PORTAL_STRUTS), spec=(sizes, centred_rect, draw_struts, PORTAL_STRUTS))
            b.extrude('portal_struts', 'Portal struts extrude', portal_sk, New, symmetric='tower_strut_along_length', body_name='Portal strut', profile=every_profile)
            bars_sk = b.sketch('brace_bar_sketch', 'Brace bars', lambda: comp.xZConstructionPlane, lambda s: draw_brace_bars(s, brace_sk, um, out),
                               spec=(sizes, draw_brace_bars), uses=['brace_strut_sketch'])
            b.extrude('brace_bars', 'Brace bars extrude', bars_sk, New, symmetric='tower_strut_along_length', body_name='Brace bar', profile=every_profile)
            corbel_sk = b.sketch('corbel_sketch', 'Corbels', lambda: comp.xZConstructionPlane, lambda s: draw_corbels(s, front, comp, um, out),
                                 spec=(sizes, draw_corbels, DETAILED_STRUTS), uses=['tower_front_sketch'])
            b.extrude('corbels', 'Corbels extrude', corbel_sk, New, symmetric='tower_strut_along_length', body_name='Corbel', profile=every_profile)
            balcony_sk = b.sketch('balcony_sketch', 'Balconies', lambda: comp.xZConstructionPlane, lambda s: draw_balconies(s, front, comp, um, out),
                                  spec=(sizes, draw_balconies), uses=['tower_front_sketch'])
            b.extrude('balconies', 'Balconies extrude', balcony_sk, New, symmetric=ALONG[1], body_name='Balcony', profile=every_profile)
            road_sk = b.sketch('road_through_sketch', 'Road through the tower', lambda: comp.xZConstructionPlane,
                               lambda s: draw_struts(s, comp, um, out, ROAD_THROUGH), spec=(sizes, centred_rect, draw_struts, ROAD_THROUGH))
            b.extrude('road_through', 'Road through the tower extrude', road_sk, New, symmetric=ALONG[1], body_name='Road through the tower',
                      profile=every_profile)
            # The first body is the first leg; everything after it joins it.
            bodies = comp.bRepBodies
            b.combine('tower_join', 'Tower join', lambda: bodies.item(0), lambda: [bodies.item(i) for i in range(1, bodies.count)], Join,
                      body_name=TOWER, uses=['second_leg', 'brace_struts', 'portal_struts', 'brace_bars', 'corbels', 'balconies', 'road_through'])
        with b.group('Tower · strut details'):
            # Flutes in the upper band of each portal strut's faces, a recessed panel below them.
            detail_keys = []
            for prefix, bottom, top, A in DETAILED_STRUTS:
                band = FLUTED_BAND % (top, bottom)
                pl = b.offset_plane(prefix + '_flute_plane', '%s strut flutes middle' % prefix.replace('_', ' ').capitalize(), comp.xYConstructionPlane, '%s - tower_portal_strut_ledge_height - %s / 2' % (top, band))
                flute_sk = b.sketch(prefix + '_flute_sketch', '%s strut flute' % prefix.replace('_', ' ').capitalize(), lambda pl=pl: pl,
                                    lambda s, A=A: draw_flute(s, comp, A, um, out), spec=(sizes, draw_flute, A), uses=[prefix + '_flute_plane'])
                # The flute cuts the tower itself and the pattern repeats the cut. The flute count changes with
                # the sizes, and patterned cutter bodies would miss a later cut's fixed list of tools.
                b.extrude(prefix + '_flute', '%s strut flute cut' % prefix.replace('_', ' ').capitalize(), flute_sk, Cut, symmetric=band,
                          participants=lambda: [main_body(comp, TOWER)], profile=every_profile, uses=['tower_join'])
                fkey = prefix + '_flute'
                b.rect_pattern(prefix + '_flute_row', '%s strut flute row' % prefix.replace('_', ' ').capitalize(),
                               lambda fkey=fkey: [b.known[fkey]],
                               comp.xConstructionAxis, 'max(1; floor((road_width - %s) / tower_portal_strut_flute_spacing))' % A, 'tower_portal_strut_flute_spacing',
                               comp.yConstructionAxis, '1', 'tower_portal_strut_flute_spacing', uses=[fkey])
                detail_keys.append(prefix + '_flute_row')
            face = b.offset_plane('strut_face_plane', 'Strut +Y face', comp.xZConstructionPlane, 'tower_strut_along_length / 2', along=1)
            panel_sk = b.sketch('strut_panel_sketch', 'Strut panels', lambda: face, lambda s: draw_strut_panels(s, comp, um, out),
                                spec=(sizes, draw_strut_panels, DETAILED_STRUTS), uses=['strut_face_plane'])
            b.extrude('strut_panels', 'Strut panel cutters', panel_sk, New, symmetric='2 * tower_portal_strut_panel_depth', body_name='Panel cutter',
                      profile=every_profile)
            b.mirror('strut_panels_back', 'Strut panel cutters, -Y face',
                   lambda: [b.body('strut_panels', i) for i in range(b.known['strut_panels'].bodies.count)],
                   lambda: comp.xZConstructionPlane, body_name='Panel cutter (-Y)', uses=['strut_panels'])
            b.combine('strut_details', 'Strut panels cut', lambda: main_body(comp, TOWER),
                      lambda: [x for x in comp.bRepBodies if x.name != TOWER], Cut,
                      uses=['tower_join', 'strut_panels_back'] + detail_keys)

    # The pier the tower stands on, from the floor up to the tower foot. Printed.
    with b.component('pier', PIER) as comp:
        with b.group('Pier · block'):
            floor = b.offset_plane('pier_floor', 'Pier floor', comp.xYConstructionPlane, '-tower_pier_height')
            pier_sk = b.sketch('pier_sketch', 'Pier outline', lambda: floor, lambda s: draw_pier(s, comp, um, out), spec=(sizes, draw_pier), uses=['pier_floor'])
            b.extrude('pier_extrude', 'Pier extrude', pier_sk, New, distance='tower_pier_height', body_name=PIER)

    # The second tower and pier: copies of the same components, so they follow every change.
    root = b.root
    with b.group('Bridge preview'):
        b.rect_pattern('preview_towers', 'Tower and pier at the far end', lambda: [b.known['tower'], b.known['pier']],
                       root.yConstructionAxis, '2', 'main_span_length', root.xConstructionAxis, '1', 'road_width', uses=['tower', 'pier'])

    # The cable anchor block at each end. Printed.
    with b.component('anchor', ANCHOR) as comp:
        with b.group('Anchor block · blocks'):
            anchor_sk = b.sketch('anchor_sketch', 'Anchor block side', lambda: comp.yZConstructionPlane, lambda s: draw_anchor(s, comp, um, out),
                                 spec=(sizes, draw_anchor))
            b.extrude('anchor_extrude', 'Anchor block extrude', anchor_sk, New, symmetric='tower_pier_across_width', body_name=ANCHOR)
            anchor_mid = b.offset_plane('anchor_middle', 'Anchor mid-span plane', comp.xZConstructionPlane, 'main_span_length / 2', along=1)
            b.mirror('anchor_far', 'Anchor block at the far end', lambda: [b.body('anchor_extrude')], lambda: anchor_mid, body_name=ANCHOR_FAR,
                   uses=['anchor_extrude', 'anchor_middle'])

    # Side-span deck at each end, tower to anchor block. Printed.
    with b.component('side_deck', SIDE_DECK) as comp:
        with b.group('Side span deck · deck'):
            side_sk = b.sketch('side_deck_sketch', 'Side span deck side', lambda: comp.yZConstructionPlane,
                               lambda s: draw_side_deck(s, b, tower_side, anchor_sk, um, out), spec=(sizes, from_part, draw_side_deck, LEVELS),
                               uses=['tower_side_sketch', 'anchor_sketch'])
            side = deck_body(b, comp, 'side_deck', side_sk, SIDE_DECK)
        with b.group('Side span deck · truss'):
            # One hole unit and one rib halfway along, each repeated along the road both ways.
            holes_sk = b.sketch('side_truss_holes_sketch', 'Side span truss holes', lambda: comp.yZConstructionPlane,
                                lambda s: draw_holes(s, side_frame(side_sk), um, out, SIDE_PANEL), spec=(sizes, draw_holes, draw_truss_unit, side_frame),
                                uses=['side_deck_sketch'])
            b.extrude('side_truss_holes', 'Side span truss holes cut', holes_sk, Cut, symmetric=THROUGH, participants=side,
                      profile=every_profile, uses=['side_deck_roadway'])
            road = tagged(side_sk, 'side_road')
            for k, sign in enumerate(('', '-')):
                b.rect_pattern('side_truss_holes_row_%d' % (k + 1), 'Side span truss holes row, %s' % ('one way', 'other way')[k],
                               lambda: [b.known['side_truss_holes']], road, SIDE_UNITS, sign + '2 * ' + SIDE_PANEL,
                               comp.xConstructionAxis, '1', 'deck_truss_vertical_spacing', uses=['side_truss_holes'])
            rib_sk = b.sketch('side_rib_sketch', 'Side span floor rib', lambda: comp.yZConstructionPlane,
                              lambda s: draw_rib(s, side_frame(side_sk), um, out), spec=(sizes, draw_rib, side_frame), uses=['side_deck_sketch'])
            b.extrude('side_rib', 'Side span floor rib extrude', rib_sk, Join, symmetric='road_width', participants=side,
                      uses=['side_truss_holes_row_1', 'side_truss_holes_row_2'])
            for k, sign in enumerate(('', '-')):
                b.rect_pattern('side_rib_row_%d' % (k + 1), 'Side span floor ribs, %s' % ('one way', 'other way')[k],
                               lambda: [b.known['side_rib']], road, RIBS % (SIDE_HALF, SIDE_PANEL), sign + SIDE_PANEL,
                               comp.xConstructionAxis, '1', 'deck_truss_vertical_spacing', uses=['side_rib'])
            side_mid = b.offset_plane('side_deck_middle', 'Side deck mid-span plane', comp.xZConstructionPlane, 'main_span_length / 2', along=1)
            b.mirror('side_deck_far', 'Side span deck at the far end', side, lambda: side_mid, body_name=SIDE_DECK_FAR,
                   uses=['side_rib_row_1', 'side_rib_row_2', 'side_deck_middle'])

    # Main-span deck, printed in 4 sections.
    with b.component('main_deck', DECK) as comp:
        with b.group('Main span deck · deck'):
            deck_sk = b.sketch('main_deck_sketch', 'Main span deck side', lambda: comp.yZConstructionPlane,
                               lambda s: draw_main_deck(s, b, tower_side, um, out), spec=(sizes, from_part, draw_main_deck, LEVELS), uses=['tower_side_sketch'])
            deck = deck_body(b, comp, 'main_deck', deck_sk, DECK)
        with b.group('Main span deck · truss'):
            # One hole unit and one rib at mid-span, each turned along the road arc both ways, about the
            # arc's centre: an axis across the road, deck_main_span_road_arc_radius under the road at mid-span.
            mid = b.offset_plane('main_deck_middle', 'Main deck mid-span plane', comp.xZConstructionPlane, 'main_span_length / 2', along=1)
            low = b.offset_plane('main_deck_arc_centre_level', 'Main deck road arc centre level', comp.xYConstructionPlane, 'deck_road_at_main_span_middle_height - deck_main_span_road_arc_radius')
            centre = b.axis('main_deck_arc_axis', 'Main deck road arc axis', 'two_planes', lambda: mid, lambda: low,
                                  uses=['main_deck_middle', 'main_deck_arc_centre_level'])
            holes_sk = b.sketch('main_truss_holes_sketch', 'Main span truss holes', lambda: comp.yZConstructionPlane,
                                lambda s: draw_holes(s, main_frame(deck_sk), um, out), spec=(sizes, draw_holes, draw_truss_unit, main_frame),
                                uses=['main_deck_sketch'])
            b.extrude('main_truss_holes', 'Main span truss holes cut', holes_sk, Cut, symmetric=THROUGH, participants=deck,
                      profile=every_profile, uses=['main_deck_roadway'])
            # One symmetric row, not one row each way: the second row cut holes into a deck the first had
            # already cut, 295 s against 0.1 s for this (fusion/rules.md rule 32). Identical gives the same deck.
            # A symmetric pattern's angle covers both sides.
            units = HOLE_UNITS % MAIN_HALF
            b.circular_pattern('main_truss_holes_row', 'Main span truss holes row',
                        lambda: [b.known['main_truss_holes']], lambda: centre, '2 * (%s) - 1' % units,
                        '2 * ((%s - 1) * 2 * deck_truss_vertical_spacing / deck_main_span_road_arc_radius * 1 rad)' % units,
                        symmetric=True, compute='identical', uses=['main_truss_holes', 'main_deck_arc_axis'])
            rib_sk = b.sketch('main_rib_sketch', 'Main span floor rib', lambda: comp.yZConstructionPlane,
                              lambda s: draw_rib(s, main_frame(deck_sk), um, out), spec=(sizes, draw_rib, main_frame), uses=['main_deck_sketch'])
            b.extrude('main_rib', 'Main span floor rib extrude', rib_sk, Join, symmetric='road_width', participants=deck,
                      uses=['main_truss_holes_row'])
            ribs = RIBS % (MAIN_HALF, 'deck_truss_vertical_spacing')
            b.circular_pattern('main_rib_row', 'Main span floor ribs',
                        lambda: [b.known['main_rib']], lambda: centre, '2 * (%s) - 1' % ribs,
                        '2 * ((%s - 1) * deck_truss_vertical_spacing / deck_main_span_road_arc_radius * 1 rad)' % ribs,
                        symmetric=True, compute='identical', uses=['main_rib', 'main_deck_arc_axis'])
        with b.group('Main span deck · sections'):
            # Cut at mid-span, then each half at its quarter point; run() names the 4 pieces from tower 1.
            b.split_body('main_deck_split_middle', 'Main deck cut at mid-span', lambda: b.body('main_deck_block'), lambda: mid,
                       uses=['main_rib_row'])
            q1 = b.offset_plane('main_deck_quarter_1', 'Main deck quarter cut plane, tower 1 half',
                         comp.xZConstructionPlane, QUARTER % ('-', MAIN_HALF), along=1)
            b.split_body('main_deck_split_quarter_1', 'Main deck cut at the tower 1 quarter', lambda: min(comp.bRepBodies, key=centre_y),
                       lambda: q1, uses=['main_deck_split_middle', 'main_deck_quarter_1'])
            q2 = b.offset_plane('main_deck_quarter_2', 'Main deck quarter cut plane, tower 2 half',
                         comp.xZConstructionPlane, QUARTER % ('+', MAIN_HALF), along=1)
            b.split_body('main_deck_split_quarter_2', 'Main deck cut at the tower 2 quarter', lambda: max(comp.bRepBodies, key=centre_y),
                       lambda: q2, uses=['main_deck_split_quarter_1', 'main_deck_quarter_2'])

    # The two main cables. Look only: the real model uses string.
    with b.component('cables', CABLES) as comp:
        with b.group('Main cables · cables'):
            cable_plane = b.offset_plane('cable_plane', 'Cable plane over the first leg', comp.yZConstructionPlane, '-road_width / 2', along=0)
            cable_sk = b.sketch('cable_sketch', 'Main cable', lambda: cable_plane, lambda s: draw_cables(s, comp, um, out),
                                spec=(sizes, draw_cables), uses=['cable_plane'])
            b.pipe('cable_main', 'Main cable, main span', lambda: tagged(cable_sk, 'main_curve'), 'main_cable_diameter', New, body_name=CABLE_MAIN, chain=False, uses=['cable_sketch'])
            b.pipe('cable_side', 'Main cable, side span', lambda: tagged(cable_sk, 'side_line'), 'main_cable_diameter', New, body_name=CABLE_SIDE, chain=False, uses=['cable_sketch'])
            cable_mid = b.offset_plane('cable_middle', 'Cable mid-span plane', comp.xZConstructionPlane, 'main_span_length / 2', along=1)
        # The hangers and their cable bands, joined to the cable they hang from (README "Cables, hangers, deck").
        main_occ, side_occ = b.known['main_deck'], b.known['side_deck']
        for key, label, curve, sk, top, occ, deck_key, body in (
                ('main', 'main span', 'main_curve', deck_sk, 'main_top', main_occ, 'main_deck_sketch', CABLE_MAIN),
                ('side', 'side span', 'side_line', side_sk, 'side_top', side_occ, 'side_deck_sketch', CABLE_SIDE)):
            lay = hanger_layout(um, key)
            core = lambda curve=curve: tagged(cable_sk, curve)
            with b.group('Main cables · hangers, %s' % label):
                # The web hangs from a thin core inside the cable, so it stays one body. A comb trims it to the
                # hangers: a core a little thicker than the web's, with a tall tooth at each hanger. The comb
                # is one body at any hanger count, so no step lists the hangers (fusion/rules.md rule 24).
                b.pipe('web_core_' + key, 'Hanger web core, %s' % label, core, '0.5 * main_cable_diameter', New,
                       body_name='Hangers, %s' % label, chain=False, uses=['cable_sketch'])
                web_sk = b.sketch('web_%s_sketch' % key, 'Hanger web, %s' % label, lambda: cable_plane,
                                  lambda s, curve=curve, sk=sk, top=top, occ=occ, lay=lay: draw_web(
                                      s, edge(s, tagged(cable_sk, curve)), edge(s, tagged(sk, top).createForAssemblyContext(occ)), lay['ends'], out),
                                  spec=(sizes, draw_web, along_curve, edge, lay['ends']), uses=['cable_sketch', deck_key])
                b.extrude('web_' + key, 'Hanger web extrude, %s' % label, web_sk, Join, symmetric='hanger_diameter', profile=biggest_profile,
                          participants=lambda key=key: [b.body('web_core_' + key)], uses=['web_core_' + key])
                # The band sleeve is solid, so the comb's core keeps the bands joined to each other.
                b.pipe('sleeve_' + key, 'Cable band sleeve, %s' % label, core, 'cable_band_thickness', New,
                       body_name='Cable bands, %s' % label, chain=False, uses=['cable_sketch'])
                for part, width, target in (('hanger', 'hanger_diameter', 'web_'), ('band', 'cable_band_length', 'sleeve_')):
                    comb = '%s_comb_%s' % (part, key)
                    b.pipe(comb, '%s comb core, %s' % (part.capitalize(), label), core, '0.6 * main_cable_diameter', New,
                           body_name='%s comb' % part.capitalize(), chain=False, uses=['cable_sketch'])
                    tooth_sk = b.sketch(comb + '_tooth_sketch', '%s comb tooth, %s' % (part.capitalize(), label), lambda: cable_plane,
                                        lambda s, lay=lay, width=width: draw_blocks(s, [lay['tooth'](width)], um, out),
                                        spec=(sizes, draw_blocks, lay['tooth'](width)), uses=['cable_plane'])
                    b.extrude(comb + '_tooth', '%s comb tooth extrude, %s' % (part.capitalize(), label), tooth_sk, Join,
                              symmetric='2 * cable_band_thickness', participants=lambda comb=comb: [b.body(comb)], uses=[comb])
                    for row, n, d in lay['rows']:
                        b.rect_pattern('%s_%s' % (comb, row), '%s comb teeth, %s, %s' % (part.capitalize(), label, row),
                                       lambda comb=comb: [b.known[comb + '_tooth']], comp.yConstructionAxis, n, d,
                                       comp.xConstructionAxis, '1', 'road_width', uses=[comb + '_tooth'])
                    b.combine('%ss_%s' % (part, key), '%ss, %s: trimmed to the comb' % (part.capitalize(), label),
                              lambda target=target, key=key: b.body(target + key), lambda comb=comb: [b.body(comb)], Intersect,
                              uses=[target + key] + ['%s_%s' % (comb, row) for row, _, _ in lay['rows']])
                b.combine('cable_%s_hung' % key, 'Hangers and bands joined to the %s cable' % label, lambda key=key: b.body('cable_' + key),
                          lambda key=key: [one_body(b, 'hangers_' + key), one_body(b, 'bands_' + key)], Join, body_name=body,
                          uses=['cable_' + key, 'hangers_' + key, 'bands_' + key])
        with b.group('Main cables · copies'):
            b.mirror('cable_side_far', 'Main cable, far side span', lambda: [one_body(b, 'cable_side_hung')], lambda: cable_mid, body_name=CABLE_SIDE_FAR,
                   uses=['cable_side_hung', 'cable_middle'])
            b.rect_pattern('cable_pair', 'Second cable', lambda: [one_body(b, 'cable_main_hung'), one_body(b, 'cable_side_hung'), b.body('cable_side_far')],
                           comp.xConstructionAxis, '2', 'road_width', comp.yConstructionAxis, '1', 'road_width',
                           uses=['cable_main_hung', 'cable_side_hung', 'cable_side_far'])




def colour(app, des, out):
    # Not part of the timeline. Towers red, cables black, the rest grey.
    grey, black, red = (['Plastic - Matte (%s)' % c, 'Plastic - Glossy (%s)' % c] for c in ('Gray', 'Black', 'Red'))
    want = {TOWER: red, PIER: grey, ANCHOR: grey, SIDE_DECK: grey, DECK: grey, CABLES: black}
    for n, names in want.items():
        found = None
        for lib in app.materialLibraries:
            for nm in names:
                try:
                    found = found or lib.appearances.itemByName(nm)
                except:
                    pass
        if not found:
            out.append('no appearance found for %s' % n)
            continue
        local = des.appearances.itemByName(found.name) or des.appearances.addByCopy(found, found.name)
        for c in des.allComponents:
            if c.name == n:
                for x in c.bRepBodies:
                    x.appearance = local


def pictures(app, des, out):
    vp = app.activeViewport
    um = des.unitsManager
    d = 200.0
    occs = list(des.rootComponent.allOccurrences)
    seen = [(o, o.isLightBulbOn) for o in occs]
    for o in occs:
        o.isLightBulbOn = True
    planes = planes_off(des)
    sketches = [(x, x.isVisible) for c in des.allComponents for x in c.sketches]
    for x, _ in sketches:
        x.isVisible = False
    mid = p3(0, um.evaluateExpression('main_span_length / 2', 'cm'), um.evaluateExpression('tower_height / 2', 'cm'))
    for name, eye in (('bridge_iso', (-d, -d * 0.8, d * 0.5)), ('bridge_side', (-d, 0, 0)), ('bridge_along_road', (0, -d, 0))):
        with cad_apprentice.slow(out, 'picture %s' % name):
            camera(vp, mid, eye, Z)
            vp.saveAsImageFile(os.path.join(OUT_DIR, 'view_%s.png' % name), 1600, 1200)
    # Each part alone: only the first copy of its component shown.
    for n, views in ((TOWER, [('tower_iso', (-d, -d, d * 0.6)), ('tower_front', (0, -d, 0)), ('tower_side', (-d, 0, 0))]),
                     (PIER, [('pier_iso', (-d, -d, d * 0.6))]),
                     (DECK, [('main_deck_iso', (-d, -d, d * 0.6)), ('main_deck_side', (-d, 0, 0))]),
                     (SIDE_DECK, [('side_deck_iso', (-d, -d, d * 0.6)), ('side_deck_side', (-d, 0, 0))]),
                     (ANCHOR, [('anchor_iso', (-d, -d, d * 0.6))])):
        first = None
        for o in occs:
            mine = first is None and o.component.name == n
            o.isLightBulbOn = mine
            first = first or (o if mine else None)
        if first is None:
            out.append('no component %s to picture' % n)
            continue
        bb = first.boundingBox
        c = p3((bb.minPoint.x + bb.maxPoint.x) / 2, (bb.minPoint.y + bb.maxPoint.y) / 2, (bb.minPoint.z + bb.maxPoint.z) / 2)
        for name, eye in views:
            with cad_apprentice.slow(out, 'picture %s' % name):
                camera(vp, c, eye, Z)
                vp.saveAsImageFile(os.path.join(OUT_DIR, 'view_%s.png' % name), 1600, 1200)
    # Close-ups where the decks meet tower 1: the whole deck is too long to show the truss.
    for o in occs:
        o.isLightBulbOn = True
    near = p3(-um.evaluateExpression('road_width / 2', 'cm'), 0, um.evaluateExpression('deck_road_at_tower_height', 'cm'))
    for name, eye in (('deck_close_iso', (-d, d * 0.8, d * 0.5)), ('deck_close_side', (-d, 0, 0)), ('deck_close_under', (-d * 0.6, d * 0.5, -d * 0.6))):
        with cad_apprentice.slow(out, 'picture %s' % name):
            camera(vp, near, eye, Z, extent=um.evaluateExpression('8 * deck_truss_vertical_spacing', 'cm'))
            vp.saveAsImageFile(os.path.join(OUT_DIR, 'view_%s.png' % name), 1600, 1200)
    # Close-ups of the hangers and their cable bands: at mid-span, where they are shortest, and by tower 1.
    ev = lambda e: um.evaluateExpression(e, 'cm')
    cell, zt = ev('deck_truss_vertical_spacing'), ev('deck_road_at_tower_height')
    mid_low = p3(near.x, ev('main_span_length / 2'), ev('deck_road_at_main_span_middle_height') + cell)
    for name, t, eye, ext in (('hangers_mid_span_iso', mid_low, (-d, d * 0.6, d * 0.45), 8 * cell),
                              ('hangers_mid_span_side', mid_low, (-d, 0, 0), 10 * cell),
                              ('hangers_near_tower_iso', p3(near.x, 6 * cell, zt + (ev('tower_height') - zt) * 0.6), (-d, d * 0.7, d * 0.3), 14 * cell),
                              ('hangers_side_span_iso', p3(near.x, -8 * cell, zt + (ev('tower_height') - zt) * 0.4), (-d, -d * 0.7, d * 0.3), 14 * cell)):
        with cad_apprentice.slow(out, 'picture %s' % name):
            camera(vp, t, eye, Z, extent=ext)
            vp.saveAsImageFile(os.path.join(OUT_DIR, 'view_%s.png' % name), 1600, 1200)
    for o, on in seen + planes:
        o.isLightBulbOn = on
    for x, on in sketches:
        x.isVisible = on
    out.append('pictures saved')




def name_sections(des, out):
    # The splits leave the main deck's 4 pieces with names Fusion picks; they are named here, from tower 1.
    for c in des.allComponents:
        if c.name != DECK:
            continue
        pieces = sorted(c.bRepBodies, key=centre_y)
        if len(pieces) != len(DECK_SECTIONS):
            out.append('MAIN DECK IN %d PIECES, not %d' % (len(pieces), len(DECK_SECTIONS)))
            return
        for x, n in zip(pieces, DECK_SECTIONS):
            x.name = n


# Details that can print thinner than one nozzle line on a small bridge. Logged as THIN after the
# build and each trial, never failed (fusion/rules.md rule 9).
THIN_WATCH = ['tower_portal_strut_flute_depth', 'tower_portal_strut_ledge_height',
              'tower_portal_strut_panel_side_border_width', 'tower_portal_strut_panel_top_bottom_border_height',
              'tower_portal_strut_panel_depth', 'tower_portal_strut_end_bracket_step_height',
              'tower_portal_strut_end_bracket_step_out_length', 'tower_balcony_edge_height',
              'deck_truss_bottom_bar_height', 'deck_truss_vertical_and_diagonal_width', 'deck_truss_side_wall_thickness',
              'deck_slab_thickness', 'deck_floor_rib_height', 'deck_floor_rib_along_length',
              'deck_railing_lip_height', 'deck_sidewalk_curb_height', 'hanger_diameter']


def cable_problems(des):
    # The cables as 6 bodies (main, side and far side, twice), none reaching above the tower tops, and
    # two of them running the whole main span. A cable sketch that didn't solve leaves a short cable
    # and loose hanger teeth taller than the towers, with every timeline step healthy.
    ev = lambda e: des.unitsManager.evaluateExpression(e, 'cm')
    M, top = ev('main_span_length'), ev('tower_height + main_cable_diameter + cable_band_thickness')
    bad = []
    for c in des.allComponents:
        if c.name != CABLES:
            continue
        bodies = list(c.bRepBodies)
        if len(bodies) != 6:
            bad.append('cables in %d bodies, not 6' % len(bodies))
        tall = [x.name for x in bodies if x.boundingBox.maxPoint.z > top]
        if tall:
            bad.append('above the tower tops: %s' % ', '.join(tall[:4]))
        whole = [x for x in bodies if x.boundingBox.minPoint.y < 0.01 * M and x.boundingBox.maxPoint.y > 0.99 * M]
        if len(whole) != 2:
            bad.append('%d cables run the whole main span, not 2' % len(whole))
        # A cable dipping into the railing lip cuts its hanger web in two, and the hangers on one side of
        # the dip are lost.
        for s in c.sketches:
            if s.name.startswith('Hanger web') and s.profiles.count != 1:
                bad.append('%s in %d pieces, not 1: the cable touches the deck top' % (s.name, s.profiles.count))
    return bad


def trial_checks(des):
    # What the build checks after finish(), checked at each trial value too: no loose piece in the
    # tower or the pier, the main deck still in its 4 sections, and the cables whole.
    bad = loose_pieces(des, (TOWER, PIER)) + cable_problems(des)
    for c in des.allComponents:
        if c.name == DECK and c.bRepBodies.count != len(DECK_SECTIONS):
            bad.append('main deck in %d pieces, not %d' % (c.bRepBodies.count, len(DECK_SECTIONS)))
    return bad


def run(context):
    out = cad_apprentice.LiveLog(LOG)
    app = adsk.core.Application.get()
    b = go_back = None
    try:
        if MODE in ('saved', 'check', 'clean'):
            doc = saved_design(app, out, SAVED_DOC, SAVED_ID)
            doc.activate()
            des = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))
            if MODE == 'clean':
                go_back = wipe(doc, des, out, FAV_ORDER, OLD_NAMES)  # A failed rebuild goes back to before the wipe.
        else:
            # A second 'new' would save a second design of the same name. 'night' saves nothing.
            if MODE == 'new' and any(f.name == SAVED_DOC for f in app.data.activeProject.rootFolder.dataFiles):
                raise Exception('%s is already saved in %s; run saved, or rename it first' % (SAVED_DOC, app.data.activeProject.name))
            with cad_apprentice.slow(out, 'new tab'):
                doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
            des = adsk.fusion.Design.cast(app.activeProduct)
            des.designType = adsk.fusion.DesignTypes.ParametricDesignType
        b = cad_apprentice.Builder(des, doc, out, go_back_to=go_back)
        cad_apprentice.progress(out, 'mode %s: building' % MODE)
        describe(b)
        if not b.finish():
            out.close()
            return
        pieces = loose_pieces(des, (TOWER, PIER))
        if pieces:
            out.append('LOOSE PIECES, a join missed a piece: %s' % '; '.join(pieces))
        for x in cable_problems(des):
            out.append('CABLE BROKEN: ' + x)
        watch =thin.Watch(THIN_WATCH, out)
        watch(des, 'build')
        cad_apprentice.progress(out, 'report: starting')
        name_sections(des, out)
        report(des, out)
        cad_apprentice.progress(out, 'colour: starting')
        colour(app, des, out)
        cad_apprentice.progress(out, 'pictures: starting')
        pictures(app, des, out)
        cad_apprentice.progress(out, 'sketch pictures: starting')
        sketch_pictures(app, des, out, OUT_DIR)
        hide_sketches(des, out)
        planes_off(des)
        out.append('construction planes and axes hidden')
        if MODE in ('saved', 'check', 'clean'):
            b.save(SAVE_NOTE)  # slow-ok: Builder.save() logs it
        elif MODE == 'new':
            # A first build is saved as a new design (fusion/rules.md rule 4).
            with cad_apprentice.slow(out, 'save as %s' % SAVED_DOC):
                doc.saveAs(SAVED_DOC, app.data.activeProject.rootFolder, 'Built by the bridge script.', '')
            out.append('saved as %s in %s' % (SAVED_DOC, app.data.activeProject.name))
        else:
            out.append('night: not saved; the tab stays open, save it by hand if you like it')
        if MODE in ('check', 'night'):
            out.append('--- rerun, should change nothing')
            b = cad_apprentice.Builder(des, doc, out)
            describe(b)
            if not b.finish():
                out.close()
                return
            if b.structure_changed or b.params_set:
                out.append('RERUN CHANGED SOMETHING, see the steps line above')
            start = set(trial_checks(des))

            def more(des):
                # The trial's label: the ranged parameters it moved off their usual values.
                usual = {p[0]: p[1] for p in PARAMS}
                moved = [(n, des.userParameters.itemByName(n).expression) for n in RANGES]
                watch(des, 'trial with ' + (', '.join('%s = %s' % x for x in moved if x[1] != usual[x[0]]) or 'usual values'))
                return [x for x in trial_checks(des) if x not in start]
            if not b.trials(only=ONLY, **TEST, stop=os.path.join(OUT_DIR, 'stop'), more=more):
                b.abort('a trial did not come back')
                out.close()
                return
            for item in b.trials_failed:
                out.append('TRIAL FAILED: ' + item)
            watch.summary()
            b.back_to_saved()
        out.append('DONE')
    except:
        out.append(traceback.format_exc())
        if b:
            b.abort('see the error above')
    out.close()
