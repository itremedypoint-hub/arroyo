#!/usr/bin/env python3
"""Structural checks on the shipped page: balanced tags, exactly one <main>
and one <h1>, every id the JS wires must exist, CSP present, no inline
event handlers (XSS discipline), lang plumbing in place."""
import re, os
from html.parser import HTMLParser
HERE = os.path.dirname(os.path.abspath(__file__))
html = open(os.path.join(HERE, "..", "site", "index.html"), encoding="utf-8").read()
N = 0
def check(cond, msg):
    global N
    assert cond, msg
    N += 1

VOID = {"area","base","br","col","embed","hr","img","input","link","meta","source","track","wbr","path","circle","line","text","desc","title_svg"}
class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.ids = [], [], []
        self.counts = {"main": 0, "h1": 0}
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d: self.ids.append(d["id"])
        for k, _ in attrs:
            if k.startswith("on"): self.errors.append(f"inline handler {k} on <{tag}>")
        if tag in self.counts: self.counts[tag] += 1
        if tag not in VOID: self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d: self.ids.append(d["id"])
    def handle_endtag(self, tag):
        if tag in VOID: return
        if not self.stack: self.errors.append(f"stray </{tag}>"); return
        top = self.stack.pop()
        if top != tag:
            self.errors.append(f"mismatch: <{top}> closed by </{tag}>")
p = P(); p.feed(html)
check(p.errors == [], f"tag errors: {p.errors[:5]}")
check(p.stack == [], f"unclosed tags: {p.stack}")
check(p.counts["main"] == 1, "exactly one <main>")
check(p.counts["h1"] == 1, "exactly one <h1>")
ids = set(p.ids)
check(len(ids) == len(p.ids), "no duplicate ids")
for need in ["lang","largeType","calm","modeBanner","basinChips","bName","bComm","provRow",
             "intensity","quick","ladder","readout","hwLine","curve","y2note","accEq",
             "preset","simStart","simStep","simExit","simOut","trainframe",
             "statusKV","selfCheckLine","buildLine","fnLangNote","fieldnotes",
             "todayMark","ringYear","ringSeason","ringCap","ringDesc","y3note",
             "live","alertsCard","rainCard","alertsBody","rainBody",
             "admPass","admGo","admMsg","admLocked","admPanel","admSelftest","admInspect",
             "admExport","admDiag","admLock","admJson","admValidate","admOut"]:
    check(need in ids, f"id #{need} present")
check("page" in ids, "#page canvas wrapper present")
check(html.index('<div id="page">') < html.index("<main") < html.index("</footer>") < html.index("</div><!-- /#page -->"), "#page wraps all visible content")
check("html,body{background:var(--ink) !important}" in html, "html/body canvas belt-and-suspenders")
check("<noscript>" in html, "noscript fallback present")
check("rotate(225" not in html, "no hardcoded season-ring rotation")
check("August 15, in post-fire year two" not in html, "no hardcoded build date in the ring description")
check("Content-Security-Policy" in html, "CSP meta present")
check("frame-ancestors" not in html, "frame-ancestors correctly left to HTTP headers (meta cannot carry it)")
check(html.count("target=\"_blank\"") == html.count("noopener noreferrer"), "every _blank link carries rel=noopener noreferrer")
check("innerHTML" not in re.sub(r'el\.innerHTML = ""', "", html).replace('innerHTML = ""', ""), "no innerHTML writes with content (textContent discipline)")
for marker in ["ARROYO_ENGINE","ARROYO_SHA256","ARROYO_STRINGS","ARROYO_TRAINING_DATA","ARROYO_VALIDATE"]:
    check(f"/*{marker}_START*/" in html and f"/*{marker}_END*/" in html, f"marker {marker} pair present")
check("AI assistance (Claude, Anthropic)" in html, "AI attribution present in the page itself")
print(f"HTML_CHECKS={N}")
print("test_html_structure: PASS")
