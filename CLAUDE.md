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

- **Constants:** `name = value`, evaluated top to bottom. A constant may use only constants above it. When the value is a formula rather than a plain number, its result shows faintly at the end of the field (`= 17.68`).
- **Quantities:** a name, a start value, and an "each step" rule, shown in that column order. Each step is the wider field, but while Start has focus the two widths swap (CSS `:has`), so long start formulas fit while typing. Every step evaluates the rules top to bottom:
  - in a rule, a quantity *above* has its value from this step, and one *below* (including the quantity itself) has its previous value;
  - so row order matters: `v` above `x` is Euler-Cromer (stable), and `x` above `v` is explicit Euler (energy grows). This is a teaching point, not a bug;
  - an empty rule means the quantity keeps its value.
- **Step 0:** first, start values are evaluated in order; they may use constants and quantities above that have a start value. Then quantities with an empty start get their value by evaluating their rule. A quantity with no start whose rule uses itself is an error.
- **Errors** are plain-language sentences attached to the row with the problem, and the field is highlighted. Keep that tone, and never show raw exception text.

## Formula language (hand-written recursive-descent parser in `compileExpr`)

- Formula fields (constant values, Start, Each step, while) rewrite as you type: `*` becomes `·`, and any whole-number power becomes superscript (`^7` → `⁷`, `^20` → `²⁰`, `^-3` → `⁻³`) once the next character isn't a digit or a point (or on leaving the field); decimal powers like `^2.5` stay as typed. The parser reads any run of superscript digits, with an optional `⁻`, as a power. This keeps formulas looking like physics, not code (decision), so there's no `·` button. Saved files may still contain `*`; the parser accepts both.
- Symbols are normalised: `·×∙⋅` become `*`; `−–—` become `-`; `÷`; `²` and `³`; `½`; `≥ ≤ ≠`; a decimal comma is accepted.
- Names are Unicode letters, digits and `_`: `ΣF`, `Δt`, `θ` and `x₁` all work.
- Implicit multiplication works: `2x`, `½m`, `2(x+1)`, `2|x|`. An unknown name that splits into known ones gets a suggestion: "Did you mean k·x?".
- `|x|` is absolute value and can be nested. `√` is a prefix operator. Available functions: sin cos tan asin acos atan sqrt abs sign exp ln log. sin, cos and tan return exactly 0 when the result is below 1e-15, so cos(90°) is 0 instead of 6e-17. `π` and `pi` are built in, and so is `deg` = π/180 (decision, instead of dsin/dcos/dtan): `sin(30 deg)`, `v0·cos(θ deg)`, and `asin(x)/deg` gives degrees. `°` is normalised to ` deg `, so `sin(30°)` works too. Students type `deg` without the mouse; `θdeg` gets "Did you mean θ·deg?".
- Comparisons (`> < >= <= == !=`, `=`) and `and`/`or` are allowed only in the run condition. Using them in a rule gives an explanatory error. `||` is not "or", because `|` means absolute value.

## Running

- **Stop after** N steps or T seconds. Time mode needs a constant named `Δt` (or `dt`), and the step count is `ceil(T/Δt)`. Switching units converts the value. The units read "steps", "sec" and "Never"; Never hides the number and runs until the while condition fails or the 20,000-step cap, and switching back restores the earlier limit.
- **While** condition (for example `y ≥ 0`): the run stops when it becomes false. Decision: the step that breaks the condition is kept, so the projectile ends slightly below the ground; that's intentional and good for class discussion.
- The Step button ignores both limits (decision). There's a hard cap of 20,000 steps.
- **Speed:** a logarithmic slider from 2 to 2,000 steps/s, plus Instant at the far right. The "Real time" checkbox sets the speed to 1/Δt steps/s. Both can change mid-run.
- Editing the model does **not** recompute an existing run (decision). The old run stays on screen; Step and Run are disabled and the status adds "model changed: Reset to run it" until Reset. Errors still show immediately. Undoing the edit back to the run's model unblocks Run. If there's no run yet (only step 0), an edit recomputes step 0 straight away. In code, `comp` is the compile behind `rows`, and `edit` is the compile of the model as it is now.

## Interface

- The control panel stays at the top while scrolling. It holds Step, Run, Replay, Reset, the step slider, the status, the stop limit, the condition and speed.
- **Panels:** every card (Constants, Quantities, each graph and track, Data) has a ⠿ grip in its header and can be dragged to any place in either column. The arrangement is `layout: [[left keys], [right keys]]`, with keys `consts`, `qs`, `data` and `p0`, `p1`... (plot index). It's saved with the model and in files, so a task file can set it. New graphs go to the right column above Data.
- **Default left column:** constants and quantities. Rows are dragged by the ⠿ handle using pointer events, so mouse and touch both work. Reordering moves the *other* rows, never the dragged one, so pointer capture isn't lost. There's a symbol bar: operators `² √ ½ ° | ( )`, a gap, then Greek letters in alphabetical order `α β Δ θ π Σ ω`.
- **Default right column:** graphs (any quantity against any other, up to 4 series), 1D tracks (positions on a line, with faint dots for every step and a marker for the current one), and the data table. Each graph and track has an **Origin** checkbox: automatic axes then include 0, and if all the data is on one side, 0 sits on the edge. It's saved as `origin: true`.
  - Axes never magnify rounding noise: a spread below a billionth (of 1, or of the values' size) is drawn as a constant, around 0 if it's that close to 0. Tick labels switch to powers of ten (`2e-9`, `1.5e6`) when the tick step is below 1e-4 or at least 1e5.
  - Graphs show dots only, with no connecting lines. Drag to zoom and double-click to reset.
  - **Keep zoom** (shown while zoomed) makes the zoom the graph's fixed axis range (`fixed: {x, y}`, `y` null for an x-only zoom), snapped to round numbers (0.03–7.96 becomes 0–8). Reset zoom and double-click return to it; **Auto axes** clears it. Changing a graph's quantity clears that axis. Saved in files, so a task file can preset axes. Full screen fills the window below the control panel, so the controls stay usable.
  - The data table only draws the rows on screen. It ignores a zero row-height measurement (the page can load hidden) and redraws via ResizeObserver. Clicking a row jumps to that step.
  - "Copy for Excel" copies tab-separated text rounded to 12 significant digits; Excel doesn't split pasted commas.
- **Header:** model name, Open, Save, Example menu. Save writes `.json` as `{app:"step-by-step", version:1, model, plots, layout}`. In claude.ai it uses the `downloads` capability; elsewhere it's a normal download. Opening or loading an example over unsaved changes asks first (Save first / Replace / Cancel). Dropping a file onto the page opens it.
- **Theme:** always light, even when the browser or OS is in dark mode (decision: Matan wants the colored theme). `color-scheme: light` keeps form controls light too. There is no dark theme. The page background is a soft lavender (`--bg: #E9E8F3`, matching the purple accent) with white cards on it.
- localStorage keys: `stepper-v1` (current model plus the unsaved flag), `stepper-speed`, `stepper-rt`.

## Hosting and task links

- Live at https://mataneld90.github.io/intro_to_numerics/ (GitHub Pages from `main`, root). Repo: `mataneld90/intro_to_numerics`, public. Commits use the GitHub noreply address.
- `?task=<name>` loads `tasks/<name>.json` (names are letters, digits, `_`, `-`). It goes through the same unsaved-changes guard as Open, then removes `?task=` from the address bar, so reloading keeps the student's work instead of reloading the task. A missing task shows a plain error note. It needs http, so the smoke tests serve the repo locally for these checks.

## Next

1. Student trial: one 45-minute lesson. The plan is in Matan's doc "Step by step: first student trial". Expect fixes from it.

## Open ideas (not decided)

- Equal axis scaling for y-against-x trajectories, which currently look stretched.
- The step slider has no label and sits next to the speed slider.
- A "submarine mode": import measured acceleration data as a column, then integrate it and watch the drift. It ties back to the speech Matan opens the topic with.
