# Step by step: numerical simulation for high-school physics

A browser tool where 11th–12th grade physics students build Euler-method simulations without writing code. They describe a model as a table of quantities, each with a rule for one time step, and the tool repeats it and plots the results.

Owner: Matan, a physics teacher. Matan makes the product and teaching decisions; Claude implements. His UI rule is minimal: remove anything that doesn't earn its place, and add no decorative hints. The interface is English only; there are no plans for Hebrew.

## Why it exists

Students who are afraid of coding ("this isn't what we came to physics for") struggled with the school's coding platform. Excel worked conceptually (one row per step) but had too much friction. The tool keeps Excel's blank page, so students still make every physics decision: which quantities, the force law, the order of updates, how to check. It removes the friction: cell references, filling formulas down, chart setup, and zooming.

An earlier version gave students fixed update rules and a force menu. It was rejected as too stiff, because students had nothing to do. Don't drift back toward wizards or presets.

## Files

- `index.html`: the whole tool. Self-contained, with no external dependencies. Vanilla JavaScript and canvas.
- `tasks/falling-ball.json`: trial task B. It deliberately has the wrong sign on the weight (`ΣF = m·g − c·v·|v|`). Never commit the solution to this public repository.
- `tests/smoke.py`: Playwright smoke tests. Run them before every push.

## Model semantics (the core; keep them stable)

- **Constants:** `name = value`, evaluated top to bottom. A constant may use only constants above it.
- **Quantities:** a name, an "each step" rule, and a start value, shown in that column order. Every step evaluates the rules top to bottom:
  - in a rule, a quantity *above* has its value from this step, and one *below* (including the quantity itself) has its previous value;
  - so row order matters: `v` above `x` is Euler-Cromer (stable), and `x` above `v` is explicit Euler (energy grows). This is a teaching point, not a bug;
  - an empty rule means the quantity keeps its value.
- **Step 0:** first, start values are evaluated in order; they may use constants and quantities above that have a start value. Then quantities with an empty start get their value by evaluating their rule. A quantity with no start whose rule uses itself is an error.
- **Errors** are plain-language sentences attached to the row with the problem, and the field is highlighted. Keep that tone, and never show raw exception text.

## Formula language (hand-written recursive-descent parser in `compileExpr`)

- Symbols are normalised: `·×∙⋅` become `*`; `−–—` become `-`; `÷`; `²` and `³`; `½`; `≥ ≤ ≠`; a decimal comma is accepted.
- Names are Unicode letters, digits and `_`: `ΣF`, `Δt`, `θ` and `x₁` all work.
- Implicit multiplication works: `2x`, `½m`, `2(x+1)`, `2|x|`. An unknown name that splits into known ones gets a suggestion: "Did you mean k·x?".
- `|x|` is absolute value and can be nested. `√` is a prefix operator. Available functions: sin cos tan asin acos atan sqrt abs sign exp ln log. `π` and `pi` are built in.
- Comparisons (`> < >= <= == !=`, `=`) and `and`/`or` are allowed only in the run condition. Using them in a rule gives an explanatory error. `||` is not "or", because `|` means absolute value.

## Running

- **Stop after** N steps or T seconds. Time mode needs a constant named `Δt` (or `dt`), and the step count is `ceil(T/Δt)`. Switching units converts the value.
- **While** condition (for example `y ≥ 0`): the run stops when it becomes false. Decision: the step that breaks the condition is kept, so the projectile ends slightly below the ground; that's intentional and good for class discussion.
- The Step button ignores both limits (decision). There's a hard cap of 20,000 steps.
- **Speed:** a logarithmic slider from 2 to 2,000 steps/s, plus Instant at the far right. The "Real time" checkbox sets the speed to 1/Δt steps/s. Both can change mid-run.
- Editing the model recomputes immediately, up to the step reached so far (`reached`).

## Interface

- The control panel stays at the top while scrolling. It holds Step, Run, Replay, Reset, the step slider, the status, the stop limit, the condition and speed.
- **Left column:** constants and quantities. Rows are dragged by the ⠿ handle using pointer events, so mouse and touch both work. Reordering moves the *other* rows, never the dragged one, so pointer capture isn't lost. There's a symbol bar: `· Σ Δ ² √ ½ π θ ω | ( )`.
- **Right column:** graphs (any quantity against any other, up to 4 series), 1D tracks (positions on a line, with faint dots for every step and a marker for the current one), and the data table.
  - Graphs show dots only, with no connecting lines. Drag to zoom and double-click to reset. Full screen fills the window below the control panel, so the controls stay usable.
  - The data table only draws the rows on screen. It ignores a zero row-height measurement (the page can load hidden) and redraws via ResizeObserver. Clicking a row jumps to that step.
  - "Copy for Excel" copies tab-separated text rounded to 12 significant digits; Excel doesn't split pasted commas.
- **Header:** model name, Open, Save, Example menu. Save writes `.json` as `{app:"step-by-step", version:1, model, plots}`. In claude.ai it uses the `downloads` capability; elsewhere it's a normal download. Opening or loading an example over unsaved changes asks first (Save first / Replace / Cancel). Dropping a file onto the page opens it.
- localStorage keys: `stepper-v1` (current model plus the unsaved flag), `stepper-speed`, `stepper-rt`.

## Next

1. Host on GitHub Pages. This is a public repository.
2. `?task=<name>` loads `tasks/<name>.json` directly, so students open a task from a link with no file handling.
3. Student trial: one 45-minute lesson. The plan is in Matan's doc "Step by step: first student trial". Expect fixes from it.

## Open ideas (not decided)

- Equal axis scaling for y-against-x trajectories, which currently look stretched.
- The step slider has no label and sits next to the speed slider.
- A "submarine mode": import measured acceleration data as a column, then integrate it and watch the drift. It ties back to the speech Matan opens the topic with.
