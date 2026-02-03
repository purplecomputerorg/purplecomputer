# Installing a Doodle AI Demo

After running `./tools/doodle-ai` on the VM, follow these steps to install the result and run it.

## 1. Copy the output from the VM

The training creates a timestamped folder like `doodle_ai_output/20260202_143022/`. Copy the whole folder to your dev machine:

```bash
scp -r vm:~/purple/doodle_ai_output/20260202_143022 ./doodle_ai_output/
```

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
./tools/install-doodle-demo --output-dir doodle_ai_output/20260202_143022
```

Options:

```bash
# Pick a specific iteration
./tools/install-doodle-demo --output-dir doodle_ai_output/20260202_143022 --iteration 3

# Change target playback duration (default: 10 seconds)
./tools/install-doodle-demo --output-dir doodle_ai_output/20260202_143022 --duration 15
```

This writes `purple_tui/demo/ai_generated_script.py`. The demo system picks it up automatically.

## 4. Commit and push to the VM

```bash
git add purple_tui/demo/ai_generated_script.py
git commit -m "Add AI-generated doodle demo"
git push
```

Then on the VM:

```bash
git pull
```

## 5. Run the demo on the VM

```bash
PURPLE_DEMO_AUTOSTART=1 ./scripts/run_local.sh
```

## 6. To revert to the default demo

Delete the generated file and commit:

```bash
git rm purple_tui/demo/ai_generated_script.py
git commit -m "Revert to default demo"
```

The demo system falls back to the hand-crafted default script.
