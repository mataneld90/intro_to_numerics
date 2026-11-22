"""Smoke tests for index.html. Run: pip install playwright && python tests/smoke.py
Uses system Chrome if CHROME is set, otherwise Playwright's bundled Chromium."""
import asyncio, functools, http.server, os, pathlib, threading
from playwright.async_api import async_playwright

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass

PAGE = (pathlib.Path(__file__).parent.parent / "index.html").resolve().as_uri()
FAILS = []

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  ({detail})" if detail and not cond else ""))
    if not cond: FAILS.append(name)

async def instant(pg):
    await pg.evaluate("document.getElementById('speed').value=100;document.getElementById('speed').dispatchEvent(new Event('input'))")

async def pcard(pg, i):
    return pg.locator(".card[data-panel=" + await pg.evaluate(f"plots[{i}].id") + "]")

async def replace_if_asked(pg):
    btn = pg.locator("#note.on button:has-text('Replace')")
    if await btn.count() and await btn.is_visible():
        await pg.click("#note button:has-text('Replace')"); await pg.wait_for_timeout(200)

async def main():
    async with async_playwright() as p:
        kw = {"executable_path": os.environ["CHROME"]} if os.environ.get("CHROME") else {}
        b = await p.chromium.launch(args=["--no-sandbox"], **kw)
        errs = []
        ctx = await b.new_context(viewport={"width": 1280, "height": 950}, accept_downloads=True)
        pg = await ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(PAGE); await pg.evaluate("localStorage.clear()"); await pg.reload(); await pg.wait_for_timeout(300)
        await instant(pg)

        # first visit is a blank model: only the Data panel, no graphs
        check("no previous run on a first visit", not await pg.is_visible("#prevWrap"))
        check("first visit is blank", await pg.evaluate("model.qs.length===1&&plots.length===0"))
        check("blank shows only Data", await pg.evaluate("[...document.querySelectorAll('.col > .card')].map(c=>c.dataset.panel).join()") == "consts,qs,data")
        check("dropdown has no Blank", await pg.evaluate("!document.querySelector('#example option[value=blank]')"))

        # Enter adds an empty row below and focuses its name
        await pg.locator("#consts .crow").nth(0).locator("input").nth(1).press("Enter"); await pg.wait_for_timeout(100)
        check("Enter adds a constant row", await pg.evaluate("model.consts.length===2&&model.consts[1].n===''&&document.activeElement===document.querySelectorAll('#consts .crow')[1].querySelector('input')"))
        await pg.locator("#qs .qrow").nth(0).locator("input").nth(2).press("Enter"); await pg.wait_for_timeout(100)
        check("Enter adds a quantity row", await pg.evaluate("model.qs.length===2&&model.qs[1].n===''"))

        await pg.select_option("#example", "spring"); await pg.wait_for_timeout(200); await replace_if_asked(pg)

        # default layout: Data at the top of the right column; the table shows 6 rows, then scrolls
        check("Data is top right", await pg.evaluate("document.getElementById('colR').firstElementChild.dataset.panel") == "data")
        await pg.click("#bRun"); await pg.wait_for_timeout(300)
        vis = await pg.evaluate("(()=>{const b=document.getElementById('tscroll');return (b.clientHeight-HEAD)/RH})()")
        check("table shows 6 rows", 5.8 < vis < 6.4, vis)
        await pg.click("#bReset"); await pg.wait_for_timeout(100)

        # spring example: 20 s at dt 0.1 = 200 steps; energy never rises (friction)
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        check("spring runs 200 steps", "Step 200 of 200" in await pg.inner_text("#status"))
        rises = await pg.evaluate("(()=>{const i=comp.names.indexOf('E');let n=0;for(let k=1;k<rows.length;k++)if(rows[k][i]>rows[k-1][i]+1e-12)n++;return n})()")
        check("spring energy monotonic", rises == 0, rises)

        # an edit after a run keeps the old run and blocks Run until Reset
        e_before = await pg.evaluate("rows[200][comp.names.indexOf('E')]")
        await pg.evaluate("(()=>{const q=model.qs;const iv=q.findIndex(r=>r.n==='v'),ix=q.findIndex(r=>r.n==='x');[q[iv],q[ix]]=[q[ix],q[iv]];structural();})()")
        await pg.wait_for_timeout(300)
        kept = await pg.evaluate("rows.length===201&&rows[200][comp.names.indexOf('E')]")
        check("edit keeps the old run", kept == e_before, kept)
        check("edit blocks Run", await pg.is_disabled("#bRun") and await pg.is_disabled("#bStep"))
        check("Reset is highlighted after an edit", await pg.evaluate("document.getElementById('bReset').classList.contains('primary')"))
        check("status says model changed", "model changed" in await pg.inner_text("#status"))
        await pg.evaluate("(()=>{const q=model.qs;const iv=q.findIndex(r=>r.n==='v'),ix=q.findIndex(r=>r.n==='x');[q[iv],q[ix]]=[q[ix],q[iv]];structural();})()")
        await pg.wait_for_timeout(300)
        check("undoing the edit unblocks Run", not await pg.is_disabled("#bRun"))
        await pg.evaluate("(()=>{const q=model.qs;const iv=q.findIndex(r=>r.n==='v'),ix=q.findIndex(r=>r.n==='x');[q[iv],q[ix]]=[q[ix],q[iv]];structural();})()")
        await pg.wait_for_timeout(300)

        # row order: moving x above v (explicit Euler) makes energy grow, after Reset and Run
        await pg.click("#bReset"); await pg.wait_for_timeout(100)
        check("Reset is plain again after Reset", not await pg.evaluate("document.getElementById('bReset').classList.contains('primary')"))
        check("reset unblocks Run", not await pg.is_disabled("#bRun"))
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        grows = await pg.evaluate("(()=>{const i=comp.names.indexOf('E');return rows[rows.length-1][i]>rows[0][i]})()")
        check("explicit Euler gains energy", grows)

        # previous run: Reset keeps the discarded run, drawn faded on graphs; loading another model clears it
        n_before = await pg.evaluate("rows.length")
        await pg.evaluate("model.consts.find(c=>c.n==='b').v='0';structural()"); await pg.wait_for_timeout(100)
        await pg.click("#bReset"); await pg.click("#bRun"); await pg.wait_for_timeout(300)
        check("Reset keeps the previous run", await pg.evaluate("prev&&prev.rows.length") == n_before)
        check("Previous run checkbox shows", await pg.is_visible("#prevWrap") and await pg.is_checked("#showPrev"))
        check("previous run is drawn on matching graphs", await pg.evaluate("prevPairs(plots[0]).length===1&&prevPairs(plots[2]).length===1"))
        await pg.click("#bReset"); await pg.wait_for_timeout(100)
        check("a second Reset doesn't replace it with an empty run", await pg.evaluate("prev.rows.length") > 1)
        await pg.click("#bRun"); await pg.wait_for_timeout(300)
        await pg.uncheck("#showPrev")
        check("unchecking hides it", await pg.evaluate("prevPairs(plots[0]).length===0"))
        await pg.check("#showPrev")
        await pg.evaluate("model.consts.find(c=>c.n==='b').v='0.3';structural()"); await pg.click("#bReset"); await pg.click("#bRun"); await pg.wait_for_timeout(300)

        # Axes row: typed from/to ranges, blank = automatic, saved; zoom is temporary on top
        card = await pcard(pg, 0)
        await card.locator("button:has-text('Axes')").click()
        row = card.locator(".axrow")
        check("Axes opens a row", await row.is_visible() and await row.locator(".axname").first.inner_text() == "t")
        xs = row.locator("input[data-ax=x]")
        await xs.nth(0).fill("0"); await xs.nth(1).fill("8"); await xs.nth(1).press("Enter"); await pg.wait_for_timeout(100)
        m = await pg.evaluate("[plots[0].fixed, plots[0]._map.x0, plots[0]._map.x1]")
        check("typed range sets the axis", m == [{"x": [0, 8], "y": None}, 0, 8], m)
        ys = row.locator("input[data-ax=y]")
        await ys.nth(0).fill("−0.5"); await ys.nth(0).press("Enter"); await pg.wait_for_timeout(100)
        m = await pg.evaluate("[plots[0].fixed.y, plots[0]._map.y0, plots[0]._map.y1>0]")
        check("one end only, other automatic", m == [[-0.5, None], -0.5, True], m)
        await pg.evaluate("plots[0].view={x:[1,2]};drawAll()")
        await card.locator("canvas").dblclick()
        check("zoom then double-click returns to typed range", await pg.evaluate("plots[0].view===null&&plots[0]._map.x1===8"))
        check("typed range is saved", await pg.evaluate("JSON.parse(localStorage.getItem('stepper-v1')).plots[0].fixed.x[1]===8"))
        await xs.nth(0).fill("9"); await xs.nth(0).press("Enter"); await pg.wait_for_timeout(100)
        check("from above to is refused", await pg.evaluate("plots[0].fixed.x[0]===0") and "bad" in (await xs.nth(0).get_attribute("class")))
        await xs.nth(0).fill("0"); await xs.nth(1).fill("2*k"); await xs.nth(1).press("Enter"); await pg.wait_for_timeout(100)
        m = await pg.evaluate("[plots[0].fixed.x, plots[0]._map.x1]")
        check("a formula of constants sets the axis", await xs.nth(1).input_value() == "2·k" and m == [[0, "2·k"], 8], (await xs.nth(1).input_value(), m))
        await pg.evaluate("model.consts.find(c=>c.n==='k').v='5';structural()"); await pg.wait_for_timeout(100)
        check("the axis follows the constant", await pg.evaluate("plots[0]._map.x1") == 10)
        await pg.evaluate("model.consts.find(c=>c.n==='k').v='4';structural()"); await pg.wait_for_timeout(100)
        await xs.nth(0).fill("x"); await xs.nth(0).press("Enter"); await pg.wait_for_timeout(100)
        check("a quantity is refused", "bad" in (await xs.nth(0).get_attribute("class")) and await xs.nth(0).get_attribute("title") == "Only constants can be used in axis ranges.")
        for k in range(2):
            await xs.nth(k).fill(""); await ys.nth(k).fill("")
        await ys.nth(1).press("Enter"); await pg.wait_for_timeout(100)
        check("clearing all fields gives automatic axes", await pg.evaluate("plots[0].fixed===null"))
        check("no Keep zoom button", await card.locator("button:has-text('Keep zoom')").count() == 0)
        await card.locator("button:has-text('Axes')").click()

        # columns: Name, Start, Each step
        heads = await pg.evaluate("[...document.querySelectorAll('.qhead span')].map(s=>s.textContent).filter(Boolean)")
        check("quantity columns order", heads == ["Name", "Start", "Each step"], heads)
        check("start is in the 2nd field", await pg.locator("#qs .qrow").nth(0).locator("input").nth(1).input_value() == "0")

        # symbols
        syms = await pg.evaluate("[...document.querySelectorAll('#syms button')].map(b=>b.textContent).join('')")
        check("symbol bar", syms == "²√½°|()αβΔθπΣω", syms)

        # typing * and ^2 gives physics notation; ^20 stays
        f = pg.locator("#qs .qrow").nth(5).locator("input").nth(2)
        old = await f.input_value()
        await f.fill(""); await f.press_sequentially("m*v^2/2")
        check("* and ^2 become · and ² while typing", await f.input_value() == "m·v²/2", await f.input_value())
        await f.fill(""); await f.press_sequentially("x^2 + y^20")
        await f.blur()
        check("^2 and ^20 convert whole", await f.input_value() == "x² + y²⁰", await f.input_value())
        await f.fill(""); await f.press_sequentially("0.01^7-20 + 10^-3·k + x^2.5"); await f.blur()
        check("any whole power converts, decimals stay", await f.input_value() == "0.01⁷-20 + 10⁻³·k + x^2.5", await f.input_value())
        sv = await pg.evaluate("['0.01⁷-20','10⁻³','2²⁰','x²'].map(s=>compileExpr(s,new Set(['x'])).f({x:3}))")
        check("superscript powers calculate", sv == [0.01**7 - 20, 0.001, 2**20, 9], sv)
        await f.fill(""); await f.press_sequentially("v^3"); await f.blur(); await pg.wait_for_timeout(100)
        check("^3 at the end converts on leaving the field", await f.input_value() == "v³", await f.input_value())
        await f.fill(old); await pg.wait_for_timeout(300)
        await pg.locator("#cond").press_sequentially("x*2 > 0")
        check("while field converts too", await pg.input_value("#cond") == "x·2 > 0", await pg.input_value("#cond"))
        await pg.fill("#cond", ""); await pg.wait_for_timeout(100)

        # a constant written as a formula shows its value; a plain number doesn't
        await pg.evaluate("model.consts.push({n:'w',v:'√(k/m)'});structural()"); await pg.wait_for_timeout(200)
        check("formula constant shows its value", await pg.inner_text("#val-c4") == "= 2")
        check("plain constant shows nothing", await pg.inner_text("#val-c0") == "")
        await pg.evaluate("model.consts.pop();structural()"); await pg.wait_for_timeout(200)

        # the field being typed in gets the wider column
        start = pg.locator("#qs .qrow").nth(0).locator("input").nth(1)
        await start.focus(); await pg.wait_for_timeout(300)
        ws = await pg.evaluate("[...document.querySelectorAll('#qs .qrow')[0].querySelectorAll('input')].map(i=>i.offsetWidth)")
        check("focused Start widens", ws[1] > ws[2], ws)
        await start.blur(); await pg.wait_for_timeout(300)

        # origin toggle: E is always positive, so with origin its axis starts at 0
        await (await pcard(pg,2)).locator("input[data-role=origin]").check()
        y0 = await pg.evaluate("plots[2]._map.y0")
        check("origin puts 0 on the axis", y0 == 0, y0)
        check("origin is saved", await pg.evaluate("JSON.parse(localStorage.getItem('stepper-v1')).plots[2].origin===true"))

        # panels: drag the first graph to the top of the left column
        g = await (await pcard(pg, 0)).locator(".cgrip").bounding_box()
        c = await pg.locator(".card[data-panel=consts]").bounding_box()
        await pg.mouse.move(g["x"] + 4, g["y"] + 6); await pg.mouse.down()
        await pg.mouse.move(c["x"] + 40, c["y"] + 10, steps=8); await pg.mouse.move(c["x"] + 40, c["y"] + 5, steps=2); await pg.mouse.up()
        lay = await pg.evaluate("layoutSpec()")
        check("drag moves a panel to the other column", lay[0][0] == "p0", lay)
        check("layout is saved", await pg.evaluate("JSON.parse(localStorage.getItem('stepper-v1')).layout[0][0]==='p0'"))
        await pg.reload(); await pg.wait_for_timeout(300)
        check("layout survives reload", await pg.evaluate("document.getElementById('colL').firstElementChild.dataset.panel===plots[0].id"))

        # error messages
        rule = pg.locator("#qs .qrow").nth(1).locator("input").nth(2)
        await rule.fill("−kx − b·v"); await pg.wait_for_timeout(400)
        check("implicit-name suggestion", "Did you mean k·x" in await pg.inner_text("#err-q1"))
        await rule.fill("−k·x − b·v"); await pg.wait_for_timeout(400)

        # projectile with while y >= 0
        await pg.select_option("#example", "projectile"); await pg.wait_for_timeout(200); await replace_if_asked(pg)
        check("loading another model clears the previous run", await pg.evaluate("prev===null") and not await pg.is_visible("#prevWrap"))
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        st = await pg.inner_text("#status")
        check("condition stops projectile", "became false" in st and "Step 147" in st, st)

        # Stop after: Never relies on the condition; switching back restores the time
        await pg.select_option("#runUnit", "never"); await pg.wait_for_timeout(100)
        check("never hides the number", not await pg.is_visible("#runN"))
        await pg.click("#bReset"); await pg.click("#bRun"); await pg.wait_for_timeout(200)
        check("never still stops on the condition", "Step 147" in await pg.inner_text("#status"))
        await pg.select_option("#runUnit", "time"); await pg.wait_for_timeout(100)
        check("leaving never restores the value", await pg.input_value("#runN") == "10")

        # parser
        vals = await pg.evaluate("""(()=>{const k=new Set(['x','v']);const e={x:-0.5,v:-2};
          return ['|x|','2|x|','||x|−1|','√|x|','½·v²','2(x+1)'].map(s=>compileExpr(s,k).f(e))})()""")
        check("parser values", [round(v, 6) for v in vals] == [0.5, 1, 0.5, 0.707107, 2, 1], vals)
        degs = await pg.evaluate("""(()=>{const k=new Set(['θ']);const e={θ:30};
          return ['sin(30 deg)','sin(30°)','sin(θ deg)','2sin(θ°)','asin(0.5)/deg','cos(60deg)'].map(s=>compileExpr(s,k).f(e))})()""")
        check("degrees", [round(v, 9) for v in degs] == [0.5, 0.5, 0.5, 1, 30, 0.5], degs)
        check("cos(90°) is exactly 0", await pg.evaluate("compileExpr('cos(90°)',new Set()).f({})") == 0)
        r = await pg.evaluate("range([0,3e-17,6e-17,1e-16])")
        check("noise range shows as constant", r == [-1, 1], r)
        ticks = await pg.evaluate("[fmtTick(2e-9,1e-9),fmtTick(1.5e-9,5e-10),fmtTick(1.5e6,5e5),fmtTick(0,1e-9),fmtTick(2.5,0.5)]")
        check("tick labels", ticks == ["2e-9", "1.5e-9", "1.5e6", "0", "2.5"], ticks)
        sug = await pg.evaluate("(()=>{try{compileExpr('sin(θdeg)',new Set(['θ']))}catch(e){return e.message}})()")
        check("θdeg suggests θ·deg", "Did you mean θ·deg" in sug, sug)
        cond = await pg.evaluate("compileExpr('|x| < 1 and v ≥ −2',new Set(['x','v']),true).f({x:-0.5,v:-2})")
        check("condition parser", cond == 1)

        # save then open round-trip
        await pg.fill("#title", "Round trip")
        async with pg.expect_download() as d:
            await pg.click("#bSave")
        dl = await d.value; path = str(pathlib.Path(__file__).parent / "_tmp.json"); await dl.save_as(path)
        await pg.select_option("#example", "spring"); await pg.wait_for_timeout(200); await replace_if_asked(pg)
        await pg.set_input_files("#fileIn", path); await pg.wait_for_timeout(300); await replace_if_asked(pg)
        check("save/open round trip", await pg.input_value("#title") == "Round trip")
        os.remove(path)

        # task file
        await pg.set_input_files("#fileIn", str(pathlib.Path(__file__).parent.parent / "tasks/falling-ball.json"))
        await pg.wait_for_timeout(300); await replace_if_asked(pg)
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        y = await pg.evaluate("rows[rows.length-1][comp.names.indexOf('y')]")
        check("task B bug makes the ball rise", y > 100, y)

        # ?task= links (need http, so serve the repo locally)
        root = str(pathlib.Path(__file__).parent.parent)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=root))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}/index.html"
        await pg.goto(base); await pg.evaluate("localStorage.clear()")
        await pg.goto(base + "?task=falling-ball"); await pg.wait_for_timeout(500)
        check("task link loads the task", await pg.input_value("#title") == "Task B: a falling ball")
        check("task link clears the query", "task=" not in pg.url, pg.url)
        await pg.fill("#title", "Student work"); await pg.wait_for_timeout(100)
        await pg.goto(base + "?task=falling-ball"); await pg.wait_for_timeout(500)
        check("task link asks before replacing work", await pg.locator("#note.on button:has-text('Replace')").count() == 1)
        await pg.click("#note button:has-text('Cancel')")
        check("cancel keeps the work", await pg.input_value("#title") == "Student work")
        await pg.goto(base + "?task=nope"); await pg.wait_for_timeout(500)
        # find-the-bug tasks B2-B7: each opens by its link and shows its symptom (symptoms only, never fixes)
        async def run_task(name):
            await pg.goto(base); await pg.evaluate("localStorage.clear()")
            await pg.goto(base + "?task=" + name); await pg.wait_for_timeout(500)
            await instant(pg); await pg.click("#bRun"); await pg.wait_for_timeout(300)
            return await pg.evaluate("""(()=>{const N=comp.names,col=n=>rows.map(r=>r[N.indexOf(n)]);const o={title:model.title,sel:document.getElementById('example').value};
              for(const n of N){const c=col(n);o[n]=c[c.length-1];o[n+'0']=c[0];o[n+'max']=Math.max(...c);o[n+'min']=Math.min(...c);}return o})()""")
        r = await run_task("spring")
        check("B2 opens", r["title"] == "Task B2: a mass on a spring" and r["sel"] == "task:spring", r["title"])
        check("B2 symptom: x falls and never comes back", abs(r["x"] + 200) < 1 and r["x"] == r["xmin"], r["x"])
        r = await run_task("damped-spring")
        check("B3 opens", r["title"] == "Task B3: a spring with friction", r["title"])
        check("B3 symptom: energy grows from 2 to about 860", r["E0"] == 2 and 850 < r["E"] < 870, r["E"])
        r = await run_task("balcony-throw")
        check("B4 opens", r["title"] == "Task B4: a ball thrown up from a balcony", r["title"])
        check("B4 symptom: peaks near 10.2 m, stops near 0.24 s", abs(r["ymax"] - 10.2) < 0.05 and abs(r["t"] - 0.24) < 1e-9, (r["ymax"], r["t"]))
        r = await run_task("balcony-throw-2")
        check("B5 opens", r["title"] == "Task B5: another ball thrown up from a balcony", r["title"])
        check("B5 symptom: y never rises, stops near 1.04 s", r["ymax"] == 10 and abs(r["t"] - 1.04) < 1e-9, (r["ymax"], r["t"]))
        r = await run_task("cart")
        check("B6 opens", r["title"] == "Task B6: a cart pushed by a constant force", r["title"])
        check("B6 symptom: x(4 s) about 48.6, v(4 s) = 24", abs(r["x"] - 48.6) < 0.01 and abs(r["v"] - 24) < 1e-9, (r["x"], r["v"]))
        r = await run_task("dropped-ball")
        check("B7 opens", r["title"] == "Task B7: a ball dropped from 45 m", r["title"])
        check("B7 symptom: stops near 0.96 s", abs(r["t"] - 0.96) < 1e-9, r["t"])

        await pg.goto(base); await pg.wait_for_timeout(300)
        await pg.select_option("#example", "task:falling-ball"); await pg.wait_for_timeout(500); await replace_if_asked(pg)
        check("Task B from the dropdown", await pg.input_value("#title") == "Task B: a falling ball" and await pg.input_value("#example") == "task:falling-ball")
        await pg.click("#bNew"); await pg.wait_for_timeout(200); await replace_if_asked(pg)
        check("New gives a blank model", await pg.evaluate("model.qs.length===1&&plots.length===0") and await pg.input_value("#title") == "")
        await pg.goto(base + "?task=nope"); await pg.wait_for_timeout(500)
        check("missing task shows an error", "Couldn't open the task" in await pg.inner_text("#note"))
        srv.shutdown()

        # a browser in dark mode still gets the light theme
        dctx = await b.new_context(color_scheme="dark")
        dpg = await dctx.new_page(); await dpg.goto(PAGE); await dpg.wait_for_timeout(200)
        bg = await dpg.evaluate("getComputedStyle(document.body).backgroundColor")
        check("light theme in a dark browser", bg == "rgb(233, 232, 243)", bg)
        await dctx.close()

        check("no page errors", not errs, errs)
        await b.close()
    print("\nFAILED: " + ", ".join(FAILS) if FAILS else "\nAll passed")

asyncio.run(main())
