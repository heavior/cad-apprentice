# cad-apprentice: for agents

You design parts in Autodesk Fusion with a person, from a Python build script.

1. **Read [README.md](README.md) first,** for what the kit does and the process. Then, before you
   write or change any script, **read [lib/README.md](fusion/lib/README.md):** how a script is built, every
   step the library has, how a run works and how to read a failed one.
2. **Follow [fusion/rules.md](fusion/rules.md) on every CAD job.** It covers working with the
   person, sketches, parameters, the timeline, build scripts and running them.
3. **Follow [3dprinting/rules.md](3dprinting/rules.md)** when a design is approved for
   printing.
4. **Start a new design with `new`,** from the repo root:
   `python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py new NAME PROJECT_DIR --doc "Design name"`.
   It writes the entry file, its manifest and a starter `build.py` (a rounded block with every mode)
   into `PROJECT_DIR/scripts/fusion/NAME/`, and copies the entry file into Fusion's Scripts folder.
   Then replace the block with the real design.
5. **Run designs with the runner,** in a background shell, from the repo root:
   `python3 projects/hobby/cad-apprentice/fusion/tools/fusion_outputs.py run NAME --mode saved`. It checks the
   script first and stops on a problem. `collect` copies the pictures and STLs into the project.
   Every tool and its options: [fusion/tools/README.md](fusion/tools/README.md).

To set up the kit on a new computer, follow [SETUP.md](SETUP.md).

The [demos](demos/) are full design projects made with the kit. You don't need to read them to work.

## Evolving the library

The library grows with each design. When a design needs something the library lacks, add it to the
library, not to the design script.

- **What goes in:** a new step type, a helper or a check that other designs can use as is, with no
  project-specific details. Everything project-specific (shapes, sizes, names) stays in the design's
  own script.
- **A new step type:** follow [Adding a step type](fusion/lib/README.md#adding-a-step-type). In short: put
  every value it sets in `spec`, wrap slow Fusion calls in `slow()`, raise on any refusal, add it to
  precheck's `STEPS`, add a test and run it through the runner, and list it in both READMEs.
- **A change to existing library code:** run the library tests through the runner before you commit
  ([tests/README.md](fusion/tests/README.md)). Never test library changes on a person's saved design.
- **A run that cost time in a new way:** add the fix to
  [Faster iterations](fusion/lib/README.md#faster-iterations).

## The kit's own README

The library and fusion/rules.md ship together, for AI agents: the rules count as features. Measure a
benefit by how many times the designer has to step in and by the time from ask to finished design, not
by seconds per run. The README's pitch is human-friendly CAD, fast. Key features comes first in
Contents, in three groups the user picked: Human-friendly, Fast robust designs and Faster agentic
work. No filler lines on what a feature saves; the feature says it. Then How to start, which also walks through the process, then the suspension bridge as the demo. Other AI CAD projects also check results and show renders, so those don't lead.
