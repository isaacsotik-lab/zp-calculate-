# Генератор синтетических справок 2-НДФЛ для проверки калькулятора.
# Все данные вымышлены. Форматы: XML (старый СвНА/НДФЛ-2 UTF-8, новый 4.02 СвНП/СправДох cp1251),
# PDF (как у Госуслуг и как у 1С), ZIP с Госуслуг, плюс негативные файлы.
import os, io, json, zipfile, random
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.dirname(os.path.abspath(__file__))
pdfmetrics.registerFont(TTFont("DV", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def esc(s): return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")

# ---------- модель справки ----------
def doc(year, org, inn, kpp, items, corr="00", num="1", rate_sections=None):
    """items: [(месяц, код, сумма, вычет_код|None, вычет_сумма)], rate_sections: {ставка: items}"""
    return dict(year=year, org=org, inn=inn, kpp=kpp, corr=corr, num=num,
                sections=rate_sections or {13: items})

def xml_old(docs):
    """Старый формат (как реальные справки с Госуслуг 2025–2026): Документ/СвНА/СвНАЮЛ/НДФЛ-2, UTF-8, без переносов"""
    out = []
    for d in docs:
        sv = []
        for rate, items in d["sections"].items():
            tot = round(sum(i[2] for i in items), 2)
            ded = round(sum(i[4] for i in items if i[3]), 2)
            rows = "".join(
                f'<СвСумДох Месяц="{m}" КодДоход="{c}" СумДоход="{v:.2f}">' + (f'<СвСумВыч КодВычет="{dc}" СумВычет="{dv:.2f}"/>' if dc else "") + "</СвСумДох>"
                if dc else f'<СвСумДох Месяц="{m}" КодДоход="{c}" СумДоход="{v:.2f}"/>'
                for (m, c, v, dc, dv) in items)
            tax = round((tot - ded) * rate / 100)
            sv.append(f'<СведДох Ставка="{rate}"><СумИтНалПер СумДохОбщ="{tot:.2f}" НалБаза="{tot-ded:.2f}" НалИсчисл="{tax}" НалУдерж="{tax}" НалУдержЛиш="0" СумФикс="0" СумНалПрибЗач="0" СумНалИнГос="0"/><НалВычССИ/><ДохВыч>{rows}</ДохВыч><СумДохНеУд СумДохНеУдерж="0" СумНеУдНал="0"/></СведДох>')
        out.append(f'<Документ ДатаДок="29.10.2026" ОтчетГод="{d["year"]}" Признак="1"><СвНА ОКТМО="45000000" Тлф="84950000000"><СвНАЮЛ НаимОрг="{esc(d["org"])}  " ИННЮЛ="{d["inn"]}" КПП="{d["kpp"]}"><СвРеоргЮЛ/></СвНАЮЛ></СвНА><НДФЛ-2 НомСпр="{d["num"]}" НомКорр="{d["corr"]}"><ПолучДох ИННФЛ="000000000000" Статус="1" ДатаРожд="01.01.1995" Гражд="643"><ФИО Фамилия="ТЕСТОВА" Имя="АННА" Отчество="СЕРГЕЕВНА"/><УдЛичнФЛ КодУдЛичн="21" СерНомДок="00 00 000000"/></ПолучДох>{"".join(sv)}</НДФЛ-2></Документ>')
    body = "".join(out)
    if len(docs) > 1:
        body = f'<Файл ИдФайл="TEST" ВерсФорм="5.05" КолДок="{len(docs)}">{body}</Файл>'
    return body.encode("utf-8")

def xml_new(d):
    """Новый формат 4.02 (как тестовые справки пользователя): Файл/Документ/СвНП/НПЮЛ/СправДох, windows-1251, с отступами"""
    rows = []
    for rate, items in d["sections"].items():
        tot = round(sum(i[2] for i in items), 2)
        r = "\n".join((f'          <СвСумДох Месяц="{m:02d}" КодДоход="{c}" СумДоход="{v:.2f}"><СвСумВыч КодВычет="{dc}" СумВычет="{dv:.2f}" /></СвСумДох>' if dc else f'          <СвСумДох Месяц="{m:02d}" КодДоход="{c}" СумДоход="{v:.2f}" />') for (m, c, v, dc, dv) in items)
        rows.append(f'      <СведДох Ставка="{rate}" КБК="18210102010011000110">\n        <СумИтНалПер СумДохОбщ="{tot:.2f}" НалБаза="{tot:.2f}" НалИсчисл="{round(tot*rate/100)}" НалУдерж="{round(tot*rate/100)}" />\n        <ДохВыч>\n{r}\n        </ДохВыч>\n      </СведДох>')
    x = f"""<?xml version='1.0' encoding='windows-1251'?>
<Файл ИдФайл="TEST" ВерсФорм="4.02" КолДок="1">
  <Документ ДатаДок="29.10.2026" ОтчетГод="{d['year']}">
    <СвНП ОКТМО="00000000">
      <НПЮЛ НаимОрг="{esc(d['org'])}" ИННЮЛ="{d['inn']}" КПП="{d['kpp']}" />
    </СвНП>
    <СправДох НомКорр="{d['corr']}">
      <ПолучДох ИННФЛ="000000000000" Статус="1" ДатаРожд="01.01.1995" Гражд="643">
        <ФИО Фамилия="ТЕСТОВА" Имя="АННА" Отчество="СЕРГЕЕВНА" />
      </ПолучДох>
{chr(10).join(rows)}
    </СправДох>
  </Документ>
</Файл>"""
    return x.encode("cp1251")

def fmt_amt(v, style):
    if style == "dot": return f"{v:.2f}"
    s = f"{v:,.2f}".replace(",", " ").replace(".", ",")
    return s

def pdf_fns(docs, style="dot"):
    """PDF как у Госуслуг: двухколоночная таблица раздела 3. Несколько справок — каждая на своей странице."""
    buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4); W, H = A4
    for d in docs:
        y = H - 40
        def t(x, yy, s, size=8): c.setFont("DV", size); c.drawString(x, yy, s)
        t(40, y, "Форма по КНД 1175018"); y -= 22
        t(150, y, "СПРАВКА О ДОХОДАХ И СУММАХ НАЛОГА ФИЗИЧЕСКОГО ЛИЦА", 10); y -= 14
        t(240, y, f"за {d['year']} год от 29.10.2026", 9); y -= 20
        t(40, y, "1. Сведения о налоговом агенте", 9); y -= 14
        t(40, y, f"Код по ОКТМО 45000000   Телефон 84950000000   ИНН {d['inn']}   КПП {d['kpp']}"); y -= 12
        t(40, y, "Налоговый агент"); t(160, y, d["org"]); y -= 20
        t(40, y, "2. Сведения о физическом лице - получателе дохода", 9); y -= 12
        t(40, y, "ИНН 000000000000"); y -= 12
        t(40, y, "Фамилия ТЕСТОВА   Имя АННА   Отчество СЕРГЕЕВНА"); y -= 20
        for rate, items in d["sections"].items():
            t(40, y, f"3. Доходы, облагаемые по ставке {rate} %", 9); y -= 14
            t(40, y, "Месяц   Код дохода   Сумма дохода   Код вычета   Сумма вычета"); t(320, y, "Месяц   Код дохода   Сумма дохода   Код вычета   Сумма вычета"); y -= 12
            half = (len(items) + 1) // 2
            L, Rr = items[:half], items[half:]
            for i in range(half):
                for (col, arr) in ((40, L), (320, Rr)):
                    if i < len(arr):
                        m, code, v, dc, dv = arr[i]
                        t(col + 4, y, str(m) if style == "dot" else f"{m:02d}")
                        t(col + 40, y, code)
                        t(col + 90, y, fmt_amt(v, style))
                        if dc: t(col + 160, y, dc); t(col + 200, y, fmt_amt(dv, style))
                y -= 11
            y -= 10
        t(40, y, "4. Стандартные, социальные и имущественные налоговые вычеты", 9); y -= 20
        t(40, y, "5. Общая сумма дохода и сумма налога", 9); y -= 12
        tot = sum(i[2] for items in d["sections"].values() for i in items)
        t(40, y, "Общая сумма дохода"); t(200, y, fmt_amt(tot, style)); t(320, y, "Налоговая база"); t(450, y, fmt_amt(tot, style)); y -= 12
        t(40, y, "Сумма налога исчисленная"); t(200, y, str(round(tot * .13)))
        c.showPage()
    c.save(); return buf.getvalue()

def pdf_scan():
    """PDF-картинка без текстового слоя (как скан)"""
    img = Image.new("RGB", (1240, 1754), "white"); dr = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT_PATH, 34)
    dr.text((120, 120), "СПРАВКА О ДОХОДАХ И СУММАХ НАЛОГА", font=f, fill="black")
    for i in range(12): dr.text((120, 260 + i * 50), f"{i+1:02d}   2000   78 500,00", font=f, fill="black")
    b = io.BytesIO(); img.save(b, "PDF"); return b.getvalue()

def gosuslugi_zip(d, fmt="old", with_pdf=True):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        base = f"EPGU_2NDFL_{d['year']}_{random.randint(10**7, 10**8)}"
        z.writestr(base + ".xml", xml_old([d]) if fmt == "old" else xml_new(d))
        z.writestr(base + "_XML.p7s", b"\x30\x82 test signature")
        if with_pdf: z.writestr(base + ".pdf", pdf_fns([d], "space"))
    return b.getvalue()

def zip_of(files):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in files: z.writestr(n, data)
    return b.getvalue()

# ---------- данные: жена, оклад 78 500, аванс 25-го, зарплата 10-го ----------
OK = 78500.0
def year_items(year, upto=12, vac=None, sick=None, bonus=None, adjust=None):
    it = []
    for m in range(1, upto + 1):
        v = OK
        if adjust and m in adjust: v = adjust[m]
        it.append((m, "2000", v, None, 0))
        if bonus and m in bonus: it.append((m, "2002", bonus[m], None, 0))
        if vac and m in vac: it.append((m, "2012", vac[m], None, 0))
        if sick and m in sick: it.append((m, "2300", sick[m], None, 0))
    return it

random.seed(7)
EMP = ("ООО «Ромашка Тест»", "7700000001", "770001001")
EMP2 = ("АО «Василёк Тест»", "7800000002", "780001001")
FUND = ("Отделение СФР по г. Москве и Московской области (тест)", "7700000003", "770101001")

# 2024: весь год у EMP, отпуск в июле, больничный в марте
d24 = doc(2024, *EMP, year_items(2024, vac={7: 36500.25}, sick={3: 6200.40}, bonus={3: 15000, 6: 15000, 9: 15000, 12: 30000}, adjust={4: 70100.0, 8: 51800.0}))
# 2025: смена работы — EMP январь–май, EMP2 с июня; оклад тот же
d25a = doc(2025, *EMP, [(m, "2000", OK, None, 0) for m in range(1, 6)] + [(5, "2013", 21430.11, None, 0), (3, "2002", 15000, None, 0)])
d25b = doc(2025, *EMP2, [(m, "2000", OK, None, 0) for m in range(6, 13)] + [(12, "2002", 30000, None, 0), (9, "2012", 38900.00, None, 0), (12, "2720", 5000.0, "501", 4000.0)])
d25b_corr = dict(d25b); d25b_corr = doc(2025, *EMP2, d25b["sections"][13] + [(11, "2002", 10000.0, None, 0)], corr="01")
d25fund = doc(2025, *FUND, [(10, "2300", 18240.50, None, 0)])
# 2026: EMP2, январь–октябрь (октябрь — текущий месяц, не должен попасть в факт)
d26 = doc(2026, *EMP2, year_items(2026, upto=10, bonus={3: 15000, 6: 15000, 9: 15000}, vac={8: 41000.00}, adjust={8: 40200.0}))
# Родственник с высоким доходом: две ставки в одной справке
big = doc(2026, "ПАО «Большие деньги Тест»", "7700000009", "770901001", None,
          rate_sections={13: [(m, "2000", 400000.0, None, 0) for m in range(1, 7)], 15: [(m, "2000", 400000.0, None, 0) for m in range(7, 10)]})

cases = {}
def put(case, name, data):
    os.makedirs(os.path.join(OUT, case), exist_ok=True)
    open(os.path.join(OUT, case, name), "wb").write(data)
    cases.setdefault(case, []).append(name)

# Сценарий A: жена, всё с Госуслуг (ZIP), смена работы, справка СФР
put("A_gosuslugi", "2ndfl-2024.zip", gosuslugi_zip(d24))
put("A_gosuslugi", "2ndfl-2025-romashka.zip", gosuslugi_zip(d25a))
put("A_gosuslugi", "2ndfl-2025-vasilek.zip", gosuslugi_zip(d25b, fmt="new"))
put("A_gosuslugi", "2ndfl-2025-sfr.zip", gosuslugi_zip(d25fund))
put("A_gosuslugi", "2ndfl-2026.zip", gosuslugi_zip(d26))
# Сценарий B: те же данные, но только PDF (как от бухгалтерии), суммы с точкой; две справки 2025 в одном PDF
put("B_pdf_only", "spravka-2024.pdf", pdf_fns([d24], "dot"))
put("B_pdf_only", "spravki-2025-dve-raboty.pdf", pdf_fns([d25a, d25b], "dot"))
put("B_pdf_only", "spravka-2025-sfr.pdf", pdf_fns([d25fund], "space"))
put("B_pdf_only", "spravka-2026.pdf", pdf_fns([d26], "space"))
# Сценарий C: корректировка — сначала исходная, потом уточнённая (НомКорр 01)
put("C_correction", "1-vasilek-2025-iskhodnaya.xml", xml_old([d25b]))
put("C_correction", "2-vasilek-2025-utochnennaya.xml", xml_old([d25b_corr]))
# Сценарий D: XML из личного кабинета налоговой с несколькими справками в одном файле
put("D_multi_xml", "lk-fns-2025.xml", xml_old([d25a, d25b, d25fund]))
# Сценарий E: высокий доход, две ставки
put("E_high_income", "2ndfl-2026-big.zip", gosuslugi_zip(big))
# Сценарий F: ошибки — скан, архив без справки, не тот файл
put("F_errors", "skan-spravki.pdf", pdf_scan())
put("F_errors", "foto-v-arkhive.zip", zip_of([("photo.jpg", b"\xff\xd8\xff\xe0 not really jpeg")]))
put("F_errors", "spisok-pokupok.txt", "молоко, хлеб".encode())
put("F_errors", "drugoy-dokument.xml", '<?xml version="1.0" encoding="utf-8"?><Заявление><Текст>не справка</Текст></Заявление>'.encode())

# ---------- ожидаемые результаты, считаются независимо от сайта ----------
BASE_LIM = {2024: 2225000, 2025: 2759000, 2026: 2979000}
CY, CM = 2026, 10
def expect(docs):
    # дедупликация: год-ИНН-КПП, побеждает большая корректировка
    by = {}
    for d in docs:
        k = (d["year"], d["inn"], d["kpp"])
        if k not in by or int(d["corr"]) >= int(by[k]["corr"]): by[k] = d
    docs = list(by.values())
    items = [(d["year"], m, c, v, dv if dc else 0, rate) for d in docs for rate, its in d["sections"].items() for (m, c, v, dc, dv) in its]
    fact = {}
    for y, m, c, v, ded, rate in items:
        if c in ("1530", "1532") or rate in (30, 35): continue
        fact[(y, m)] = fact.get((y, m), 0) + v - ded
    fact = {f"{y}-{m:02d}": round(v, 2) for (y, m), v in sorted(fact.items()) if y < CY or (y == CY and m < CM)}
    yrs = {d["year"] for d in docs}
    sick = None
    if 2024 in yrs and 2025 in yrs:
        sb = {y: sum(v for yy, m, c, v, _, _ in items if yy == y and c in ("2000", "2002", "2012", "2013")) for y in (2024, 2025)}
        sick = round((min(sb[2024], BASE_LIM[2024]) + min(sb[2025], BASE_LIM[2025])) / 730, 2)
    win = [(2025, m) for m in (10, 11, 12)] + [(2026, m) for m in range(1, 10)]
    vs = sum(v for y, m, c, v, _, _ in items if (y, m) in win and c in ("2000", "2002"))
    mons = {(y, m) for y, m, c, v, _, _ in items if (y, m) in win and c == "2000"}
    vac = round(vs / len(mons) / 29.3, 2) if len(mons) >= 10 else None
    cnt = {}
    for y, m, c, v, _, _ in items:
        age = (CY - y) * 12 + (CM - m)
        if c == "2000" and v >= 1000 and 1 <= age <= 12: cnt[round(v)] = cnt.get(round(v), 0) + 1
    best = max(cnt.items(), key=lambda kv: kv[1]) if cnt else (0, 0)
    return dict(count=len(docs), fact=fact, factMonths=len(fact), avgsick=sick, avgvac=vac, oklad=best[0] if best[1] >= 3 else 0)

exp = {
    "A_gosuslugi": expect([d24, d25a, d25b, d25fund, d26]),
    "B_pdf_only": expect([d24, d25a, d25b, d25fund, d26]),
    "C_correction": expect([d25b, d25b_corr]),
    "D_multi_xml": expect([d25a, d25b, d25fund]),
    "E_high_income": expect([big]),
}
exp["C_correction"]["corrNov"] = round(OK + 10000, 2)
json.dump({"files": cases, "expect": exp}, open(os.path.join(OUT, "expected.json"), "w"), ensure_ascii=False, indent=1)
for k, v in exp.items(): print(k, {kk: vv for kk, vv in v.items() if kk != "fact"})
