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
        check("status says model changed", "model changed" in await pg.inner_text("#status"))
        await pg.evaluate("(()=>{const q=model.qs;const iv=q.findIndex(r=>r.n==='v'),ix=q.findIndex(r=>r.n==='x');[q[iv],q[ix]]=[q[ix],q[iv]];structural();})()")
        await pg.wait_for_timeout(300)
        check("undoing the edit unblocks Run", not await pg.is_disabled("#bRun"))
        await pg.evaluate("(()=>{const q=model.qs;const iv=q.findIndex(r=>r.n==='v'),ix=q.findIndex(r=>r.n==='x');[q[iv],q[ix]]=[q[ix],q[iv]];structural();})()")
        await pg.wait_for_timeout(300)

        # row order: moving x above v (explicit Euler) makes energy grow, after Reset and Run
        await pg.click("#bReset"); await pg.wait_for_timeout(100)
        check("reset unblocks Run", not await pg.is_disabled("#bRun"))
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        grows = await pg.evaluate("(()=>{const i=comp.names.indexOf('E');return rows[rows.length-1][i]>rows[0][i]})()")
        check("explicit Euler gains energy", grows)

        # keep zoom: snapped range is kept, survives Reset zoom, and is saved
        await pg.evaluate("plots[0].view={x:[0.03,7.96]};drawAll()")
        await pg.click("#plots .card >> nth=0 >> button:has-text('Keep zoom')")
        fx = await pg.evaluate("plots[0].fixed")
        check("keep zoom snaps the range", fx == {"x": [0, 8], "y": None}, fx)
        await pg.dblclick("#plots canvas >> nth=0")
        check("double-click returns to kept range", await pg.evaluate("plots[0].view===null&&plots[0].fixed.x[1]===8"))
        check("kept range is saved", await pg.evaluate("JSON.parse(localStorage.getItem('stepper-v1')).plots[0].fixed.x[1]===8"))
        await pg.click("#plots .card >> nth=0 >> button:has-text('Auto axes')")
        check("auto axes clears it", await pg.evaluate("plots[0].fixed===null"))

        # error messages
        rule = pg.locator("#qs .qrow").nth(1).locator("input").nth(1)
        await rule.fill("−kx − b·v"); await pg.wait_for_timeout(400)
        check("implicit-name suggestion", "Did you mean k·x" in await pg.inner_text("#err-q1"))
        await rule.fill("−k·x − b·v"); await pg.wait_for_timeout(400)

        # projectile with while y >= 0
        await pg.select_option("#example", "projectile"); await pg.wait_for_timeout(200); await replace_if_asked(pg)
        await pg.click("#bRun"); await pg.wait_for_timeout(200)
        st = await pg.inner_text("#status")
        check("condition stops projectile", "became false" in st and "Step 147" in st, st)

        # parser
        vals = await pg.evaluate("""(()=>{const k=new Set(['x','v']);const e={x:-0.5,v:-2};
          return ['|x|','2|x|','||x|−1|','√|x|','½·v²','2(x+1)'].map(s=>compileExpr(s,k).f(e))})()""")
        check("parser values", [round(v, 6) for v in vals] == [0.5, 1, 0.5, 0.707107, 2, 1], vals)
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

        check("no page errors", not errs, errs)
        await b.close()
    print("\nFAILED: " + ", ".join(FAILS) if FAILS else "\nAll passed")

asyncio.run(main())
