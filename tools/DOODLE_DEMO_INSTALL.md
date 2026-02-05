# Installing a Doodle AI Demo

Run everything on the VM. No need to copy files back and forth.

## 1. Generate the drawing on the VM

```bash
./tools/doodle-ai
```

This creates a timestamped folder like `doodle_ai_output/20260202_143022/`.

## 2. Review the results

Check the screenshots to see what each iteration produced:

```
doodle_ai_output/20260202_143022/screenshots/
  iteration_0_blank.svg          # blank canvas
  iteration_0_blank_cropped.png
  iteration_1.svg                # attempt 1's result
  iteration_1_cropped.png
  iteration_2.svg                # attempt 2's result
  ...
```

The `_cropped.png` files show exactly what the AI saw (just the canvas area). Open these to pick your favorite iteration, or trust the AI's judgment (stored in `best_iteration.json`).

## 3. Install the demo

```bash
# Use the best iteration, target 10 seconds of playback
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022
```

Options:

```bash
# Install from a specific screenshot (uses that iteration automatically)
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022/screenshots/iteration_2b_refinement_cropped.png

# Pick a specific iteration by name
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --iteration 3

# Change target playback duration (default: 10 seconds)
./tools/install-doodle-demo --from doodle_ai_output/20260202_143022 --duration 15
```

This writes `purple_tui/demo/ai_generated_script.py`. The demo system picks it up automatically.

## 4. Commit

```bash
git add purple_tui/demo/ai_generated_script.py
git commit -m "Add AI-generated doodle demo"
```

## 5. Run the demo

```bash
make run-demo
```

## 6. To revert to the default demo

Delete the generated file and commit:

```bash
git rm purple_tui/demo/ai_generated_script.py
git commit -m "Revert to default demo"
```

The demo system falls back to the hand-crafted default script.
