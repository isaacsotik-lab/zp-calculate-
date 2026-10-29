# Полная проверка калькулятора в браузере: справки, расчёты, профили, копия, вёрстка.
import asyncio, http.server, threading, functools, json, os, sys  # запуск: python3 tests/e2e.py
from playwright.async_api import async_playwright

SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
E = json.load(open(os.path.join(HERE, "expected.json")))
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=SITE)); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://localhost:{PORT}/index.html"

ok = 0; bad = []
def check(name, cond, info=""):
    global ok
    if cond: ok += 1
    else: bad.append(f"{name} {info}")

async def fresh(b, w=390, scheme="light"):
    ctx = await b.new_context(viewport={"width": w, "height": 844}, color_scheme=scheme, permissions=["clipboard-read", "clipboard-write"])
    pg = await ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" and "favicon" not in m.text else None)
    await pg.goto(URL); await pg.wait_for_timeout(200)
    return ctx, pg, errs

async def upload(pg, files):
    await pg.evaluate("document.getElementById('ndfl').open=true")
    await pg.set_input_files("#ndflfile", files)
    for _ in range(120):
        await pg.wait_for_timeout(250)
        if "Читаю" not in await pg.inner_text("#ndflstatus"): break
    return await pg.inner_text("#ndflstatus")

def paths(case): return [os.path.join(HERE, case, f) for f in sorted(E["files"][case])]

async def state(pg):
    return await pg.evaluate("""()=>({n:N.length,ids:N.map(x=>x.id),orgs:N.map(x=>x.org),
      fact:Object.fromEntries(Object.entries(M).filter(([k,v])=>v.fact).map(([k,v])=>[k,+v.fact])),
      avgsick:S.avgsick,avgvac:S.avgvac,oklad:S.oklad})""")

def cmp_case(case, st, exp):
    check(f"{case}: число справок", st["n"] == exp["count"], f'{st["n"]} != {exp["count"]}')
    check(f"{case}: месяцев с фактом", len(st["fact"]) == exp["factMonths"], f'{len(st["fact"])} != {exp["factMonths"]}')
    diff = {k: (st["fact"].get(k), v) for k, v in exp["fact"].items() if abs((st["fact"].get(k) or 0) - v) > 0.005}
    check(f"{case}: суммы фактов", not diff, str(diff)[:300])
    if exp["avgsick"] is not None: check(f"{case}: средний больничный", abs(float(st["avgsick"] or 0) - exp["avgsick"]) < 0.005, f'{st["avgsick"]} != {exp["avgsick"]}')
    else: check(f"{case}: больничный не тронут", st["avgsick"] == "", st["avgsick"])
    if exp["avgvac"] is not None: check(f"{case}: средний отпуск", abs(float(st["avgvac"] or 0) - exp["avgvac"]) < 0.005, f'{st["avgvac"]} != {exp["avgvac"]}')
    else: check(f"{case}: отпуск не тронут", st["avgvac"] == "", st["avgvac"])
    check(f"{case}: оклад угадан", (float(st["oklad"] or 0) == exp["oklad"]) if exp["oklad"] else True, f'{st["oklad"]} != {exp["oklad"]}')

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()

        # ---------- 1. Сценарии со справками ----------
        for case in ["A_gosuslugi", "B_pdf_only", "D_multi_xml", "E_high_income"]:
            ctx, pg, errs = await fresh(b)
            check(f"{case}: мастер первого запуска виден", await pg.is_visible("#welcome"))
            msg = await upload(pg, paths(case))
            st = await state(pg)
            cmp_case(case, st, E["expect"][case])
            check(f"{case}: статус без ошибок", "Загружено" in msg, msg)
            check(f"{case}: мастер скрылся после оклада из справки", not await pg.is_visible("#welcome"))
            check(f"{case}: нет ошибок JS", not errs, str(errs)[:300])
            if case == "A_gosuslugi":
                orgs = set(st["orgs"]); check("A: названия организаций", "АО «Василёк Тест»" in orgs and "ООО «Ромашка Тест»" in orgs, str(orgs))
                # повторная загрузка не дублирует
                msg2 = await upload(pg, paths(case)[:2]); st2 = await state(pg)
                check("A: повтор не дублирует", st2["n"] == 5 and "уже были" in msg2, msg2)
                # перезагрузка не теряет и не меняет средние
                await pg.reload(); await pg.wait_for_timeout(300); st3 = await state(pg)
                check("A: после перезагрузки данные на месте", st3["n"] == 5 and st3["avgsick"] == st["avgsick"])
                # смешанная загрузка PDF поверх XML не дублирует
                msg3 = await upload(pg, paths("B_pdf_only")); st4 = await state(pg)
                check("A+B: PDF поверх ZIP не дублирует", st4["n"] == 5, str(st4["ids"]))
            if case == "E_high_income":
                await pg.click("#tabY"); await pg.wait_for_timeout(1500)
                taxes = await pg.evaluate("calcYear(2026).slice(0,9).map(c=>c.tax)")
                check("E: НДФЛ 13% до 2,4 млн", taxes[:6] == [52000] * 6, str(taxes))
                check("E: НДФЛ 15% после 2,4 млн", taxes[6:9] == [60000] * 3, str(taxes))
            await ctx.close()

        # ---------- 2. Корректировка: исходная, потом уточнённая и наоборот ----------
        for order in (1, -1):
            ctx, pg, errs = await fresh(b)
            files = paths("C_correction")[::order]
            for f in files: await upload(pg, [f])
            st = await state(pg)
            check(f"C({order}): одна справка", st["n"] == 1, str(st["ids"]))
            check(f"C({order}): ноябрь из уточнённой", abs(st["fact"].get("2025-11", 0) - E["expect"]["C_correction"]["corrNov"]) < .01, str(st["fact"].get("2025-11")))
            await ctx.close()

        # ---------- 3. Ошибки ----------
        ctx, pg, errs = await fresh(b)
        msg = await upload(pg, paths("F_errors"))
        check("F: скан распознан", "скан" in msg, msg)
        check("F: архив без справки", "в архиве нет справки" in msg, msg)
        check("F: не справка xml", "не похоже на справку" in msg, msg)
        check("F: txt не читается", "spisok-pokupok.txt" in msg, msg)
        check("F: ничего не добавилось", (await state(pg))["n"] == 0)
        check("F: нет ошибок JS", not errs, str(errs)[:300])
        await ctx.close()

        # ---------- 4. Логика расчётов ----------
        ctx, pg, errs = await fresh(b)
        r = await pg.evaluate("""()=>{
          const cnt=y=>{const o=[];for(let m=1;m<=12;m++){let n=0;for(let d=1;d<=new Date(y,m,0).getDate();d++) if(dayType(y,m,d).work) n++;o.push(n)}return o};
          return {c26:cnt(2026),c27:cnt(2027),
            pd:[payDate(2027,1,10).toDateString(),payDate(2026,11,10).toDateString(),payDate(2026,2,30).toDateString()],
            tax:[taxD(0,100000),taxD(2390000,2410000),taxD(0,2400000)],
            cap:[sickCap(2026).toFixed(2),sickCap(2027).toFixed(2)], min:sickMin(2026).toFixed(2),
            kids:[kidsDed(1),kidsDed(2),kidsDed(3)]}}""")
        check("Календарь 2026", r["c26"] == [15,19,21,22,19,21,23,21,22,22,20,22], str(r["c26"]))
        check("Календарь 2027", r["c27"] == [15,19,22,22,19,21,22,22,22,21,20,22], str(r["c27"]))
        check("Перенос выплаты с праздников (10 янв 2027 → 30 дек 2026)", r["pd"][0] == "Wed Dec 30 2026", r["pd"][0])
        check("Выплата в будний день не сдвигается", r["pd"][1] == "Tue Nov 10 2026", r["pd"][1])
        check("30 февраля → последний рабочий день", r["pd"][2] == "Fri Feb 27 2026", r["pd"][2])
        check("НДФЛ 13%", r["tax"][0] == 13000); check("НДФЛ на пороге 2,4 млн", r["tax"][1] == 1300 + 1500, str(r["tax"]))
        check("Лимит больничного 2026", r["cap"][0] == "6827.40"); check("Лимит больничного 2027", r["cap"][1] == "7860.27", r["cap"][1])
        check("Минимум больничного 2026 (МРОТ)", r["min"] == "890.73", r["min"])
        check("Вычет на детей", r["kids"] == [1400, 4200, 10200], str(r["kids"]))

        # мастер первого запуска
        await pg.fill("#wok", "78 500"); await pg.click("#wgo"); await pg.wait_for_timeout(1300)
        check("Мастер: оклад сохранён", await pg.evaluate("S.oklad") == "78500")
        check("Мастер: скрылся", not await pg.is_visible("#welcome"))
        # сценарий октября: 2 дня без оплаты, отпуск 19–21, работа в выходной, премия → «Почему меньше» сходится
        await pg.evaluate("Y=2026;Mo=10;render()")
        for d in ["12", "13"]: await pg.click(f'#grid button:text-is("{d}")')
        await pg.click('#brushes button[data-b=vac]')
        for d in ["19", "20", "21"]: await pg.click(f'#grid button:text-is("{d}")')
        await pg.click('#brushes button[data-b=sick]'); await pg.click('#grid button:text-is("27")')
        await pg.click('#brushes button[data-b=ot]'); await pg.click('#grid button:text-is("25")')
        await pg.fill("#bonus", "5000"); await pg.wait_for_timeout(1300)
        w = await pg.evaluate("""()=>{const c=calcYear(Y)[Mo-1];const e=explain(c);return {sum:e.items.reduce((a,x)=>a+x.dz,0),delta:e.delta,n:e.items.length,
           worked:c.worked,total:c.total,vac:c.vac,sick:c.sick,ot:c.ot,fin:c.fin}}""")
        check("Почему меньше: пункты складываются в разницу", abs(w["sum"] - w["delta"]) < 0.01, str(w))
        check("Табель: дни посчитаны", (w["worked"], w["total"], w["vac"], w["sick"], w["ot"]) == (16, 22, 3, 1, 1), str(w))
        shown = await pg.inner_text("#final")
        check("Сумма к доплате на экране совпадает с расчётом", shown.replace(" ", " ").startswith(f'{w["fin"]:,.2f}'.replace(",", " ").replace(".", ",")[:5]), shown + " vs " + str(w["fin"]))
        # отпуск через два месяца — одна выплата
        await pg.evaluate("""()=>{M['2026-12']={d:{28:'vac',29:'vac',30:'vac',31:'vac'},bonus:''};M['2027-01']={d:{1:'vac',2:'vac',3:'vac',4:'vac'},bonus:''};save()}""")
        vb = await pg.evaluate("vacBlocks().map(b=>[b.s.toDateString(),b.e.toDateString()])")
        check("Отпуск через Новый год — один блок", any(x[0] == "Mon Dec 28 2026" and x[1] == "Mon Jan 04 2027" for x in vb), str(vb))

        # резервная копия туда-обратно (с профилем и справками)
        code = await pg.evaluate("enc({v:3,S,M,N})")
        await pg.evaluate("localStorage.clear()"); await pg.reload(); await pg.wait_for_timeout(300)
        await pg.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
        await pg.fill("#code", "мусор " + code[:30] + "​" + code[30:] + "\n"); await pg.click("#imp"); await pg.wait_for_timeout(300)
        check("Копия восстановлена", "восстановлены" in await pg.inner_text("#bstatus") and await pg.evaluate("S.oklad") == "78500")

        # профили: данные не смешиваются
        await pg.fill("#pname", "Никита")
        await pg.fill("#pnew", "Аня"); await pg.click("#padd"); await pg.wait_for_timeout(300)
        check("Профиль: новый пустой", await pg.evaluate("S.oklad") == "" and await pg.is_visible("#welcome"))
        check("Профиль: приветствие с именем", "Аня" in await pg.inner_text("#hello"))
        await pg.fill("#wok", "65000"); await pg.click("#wgo"); await pg.wait_for_timeout(200)
        await pg.click('#proflist button:text-is("Никита")'); await pg.wait_for_timeout(300)
        check("Профиль: у Никиты свой оклад", await pg.evaluate("S.oklad") == "78500")
        await pg.click('#proflist button:text-is("Аня")'); await pg.wait_for_timeout(300)
        check("Профиль: у Ани свой оклад", await pg.evaluate("S.oklad") == "65000")
        await pg.reload(); await pg.wait_for_timeout(300)
        check("Профиль: помнится после перезагрузки", await pg.evaluate("S.oklad") == "65000" and "Аня" in await pg.inner_text("#hello"))
        # удаление данных удаляет только текущий профиль
        await pg.evaluate("document.querySelectorAll('details').forEach(d=>d.open=true)")
        await pg.click("#wipe"); await pg.click("#wipe"); await pg.wait_for_timeout(200)
        await pg.click('#proflist button:text-is("Никита")'); await pg.wait_for_timeout(300)
        check("Удаление: Никита не пострадал", await pg.evaluate("S.oklad") == "78500")
        # скрытие сумм
        await pg.click("#eye"); check("Скрытие сумм включается", await pg.evaluate("document.body.classList.contains('privacy')"))
        await pg.click("#eye")
        check("Нет ошибок JS (логика)", not errs, str(errs)[:300])
        await ctx.close()

        # ---------- 5. Вёрстка: ширины и темы ----------
        for w in (320, 375, 430, 768):
            for scheme in ("light", "dark"):
                ctx, pg, errs = await fresh(b, w, scheme)
                await pg.fill("#wok", "78500"); await pg.click("#wgo"); await pg.wait_for_timeout(1300)
                for tab in ("#tabM", "#tabY"):
                    await pg.click(tab); await pg.wait_for_timeout(900)
                    ov = await pg.evaluate("document.documentElement.scrollWidth-document.documentElement.clientWidth")
                    check(f"Нет гориз. прокрутки {w}px {scheme} {tab}", ov <= 0, str(ov))
                clip = await pg.evaluate("""()=>[...document.querySelectorAll('.amt,.navt,.hello h1')].filter(e=>e.scrollWidth>e.clientWidth+1&&getComputedStyle(e).textOverflow!=='ellipsis').map(e=>e.className||e.id)""")
                check(f"Цифры не обрезаны {w}px {scheme}", not clip, str(clip))
                if w == 320 and scheme == "dark":
                    await pg.click("#tabM"); await pg.wait_for_timeout(900); await pg.screenshot(path=os.path.join(HERE, "shot-320-dark.png"))
                if w == 375 and scheme == "light":
                    await pg.screenshot(path=os.path.join(HERE, "shot-375-light-year.png"))
                check(f"Нет ошибок JS {w} {scheme}", not errs, str(errs)[:200])
                await ctx.close()
        await b.close()

    print(f"\nПройдено: {ok}, ошибок: {len(bad)}")
    for x in bad: print(" ✗", x)
    sys.exit(1 if bad else 0)

asyncio.run(main())
