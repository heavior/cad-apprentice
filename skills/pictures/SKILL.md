---
name: pictures
description: Take gallery pictures of a finished cad-apprentice design in Autodesk Fusion (Fusion 360): views of the whole model plus close-ups of its details, cropped tight, for a README, a model listing or a post. The saved design is never changed. Use when the person asks for good pictures, renders, a gallery or close-ups of a design. The quick pictures that come with every run need no skill.
---

# Take gallery pictures

Find the kit as the cad-apprentice skill's [Find the kit](../cad-apprentice/SKILL.md#find-the-kit)
says. If it isn't set up yet, use the setup skill first.

Read Gallery pictures in `fusion/rules.md` in the kit folder and follow it. In short:

1. **Agree on the shots.** If the person didn't say which, offer a short list: the whole model from
   one or two sides, then close-ups of the details that make the design. Use the names the design
   uses for its parts.
2. **The design must be saved and open in Fusion.** The pictures are taken of its last saved
   version.
3. **Take them with `fusion/tools/gallery_shots.py`** through the runner add-in, as
   `fusion/tools/README.md` says. It inserts the design into a new tab, takes the pictures there and
   closes that tab unsaved. Check that its result says `"source modified": false`.
4. **Crop each picture** with `fusion/tools/trim_picture.py`, ratio `0`.
5. **Save them in the project's `pictures/gallery/`,** named for what they show, without the
   `view_` prefix.
6. **Show the person every picture.** Retake the ones they want changed: a new angle, closer,
   edges on or off.

Camera tips are in the same section of `fusion/rules.md`: orthographic with `fit` for the whole
model, perspective from 50–150 mm for close-ups.
