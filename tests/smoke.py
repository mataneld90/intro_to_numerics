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

        # keep zoom: snapped range is kept, survives Reset zoom, and is saved
        await pg.evaluate("plots[0].view={x:[0.03,7.96]};drawAll()")
        await (await pcard(pg,0)).locator("button:has-text('Keep zoom')").click()
        fx = await pg.evaluate("plots[0].fixed")
        check("keep zoom snaps the range", fx == {"x": [0, 8], "y": None}, fx)
        await (await pcard(pg,0)).locator("canvas").dblclick()
        check("double-click returns to kept range", await pg.evaluate("plots[0].view===null&&plots[0].fixed.x[1]===8"))
        check("kept range is saved", await pg.evaluate("JSON.parse(localStorage.getItem('stepper-v1')).plots[0].fixed.x[1]===8"))
        await (await pcard(pg,0)).locator("button:has-text('Auto axes')").click()
        check("auto axes clears it", await pg.evaluate("plots[0].fixed===null"))

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
