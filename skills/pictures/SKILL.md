---
name: pictures
description: Take gallery pictures of a finished cad-apprentice design in Autodesk Fusion (Fusion 360): views of the whole model plus close-ups of its details, cropped tight, for a README, a model listing or a post. The saved design is never changed. Use when the person asks for good pictures, renders, a gallery, close-ups or a picture of the design's settings. The quick pictures that come with every run need no skill.
---

# Take gallery pictures

Find the kit as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
says. If it isn't set up yet, use the setup skill first.

## Steps

1. **Agree on the shots.** If the person didn't say which, offer a short list (see What to show).
   Use the names the design uses for its parts.
2. **The design must be saved and open in Fusion.** The pictures are taken of its last saved
   version.
3. **Take them with [gallery_shots.py](../../fusion/tools/gallery_shots.py)** through the runner
   add-in: a request with `doc` (the saved design's tab), `out`, and a list of shots, each an eye
   and a target point in mm. How to send a request is in `fusion/tests/README.md`; the tool's
   options are in `fusion/tools/README.md`. It inserts the design as a linked part into a new tab,
   takes the pictures there and closes that tab unsaved. Check that its result says
   `"source modified": false`.
4. **Crop each picture** with [trim_picture.py](../../fusion/tools/trim_picture.py), ratio `0`, so
   each one keeps its own shape and is cropped tight.
5. **Save them in the project's `pictures/gallery/`,** named for what they show, without the
   `view_` prefix, so `collect` doesn't count them as stale. The suspension bridge demo is the
   example.
6. **Show the person every picture.** Retake the ones they want changed.

## Camera

- **The whole model:** an orthographic camera with `fit`. A perspective fit cuts off the near end.
  Edges off.
- **Close-ups:** perspective, with the eye about 50–150 mm away. Edges on.
- **One part top to bottom** (a tower): shoot a tall picture (`size` [1600, 2400]) and crop it.
- Hiding the origin in the design's own tab marks the tab as changed. That's why the tool works in a
  new tab.

## What to show

- **A few views that explain the idea,** not one of every part.
- **A picture for what's special** about the design, the same thing its description says in words.
  If there's a test print of that detail, show it next to the render.
- **To show a shape inside a part, cut it open in 3D,** never a flat 2D drawing. Cut copies of the
  bodies in a new tab that you close unsaved, never the saved design, and add a few short labels.
- **One idea per picture, big labels, a few words.** No paragraphs of text and no four-panel sheets.
  The explaining goes in the text next to the picture.
- **Plain words on public pictures,** not parameter names, and no trademarks.
- **A render must match the printed model closely.** Retake old renders after the design changes.

## A picture of the settings

When the design is shared with its settings (a listing's sliders, for example), make one picture
that shows what each setting changes:

- **One picture for all the settings,** never one per setting or per group. Draw every setting of
  one part on a single copy of it, and put the other parts' settings on the same picture.
- **A big bold label next to each dimension:** the setting's plain name, its default and its
  range.
- Take the renders and cut views with Fusion, then add the labels on top with an image library
  such as Pillow.
