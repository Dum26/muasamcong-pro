import re
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app

client = app.MuaSamCongClient()
folder = Path(__file__).resolve().parents[1] / ".export_inspection"
folder.mkdir(exist_ok=True)
source = (folder / "index.html").read_text(encoding="utf-8")
match = re.search(r'renderDetailV2Url:\s*("[^"\n]+")', source)
if match:
    url = json.loads(match.group(1))
    plans = client.search_plans("PL2600299008", max_pages=1)
    plan = next(p for p in plans if app.clean_plan_no(p.get("planNo")) == "2600299008")
    print(json.dumps(plan, ensure_ascii=False))
    params = {key: plan.get(key, "undefined") for key in (
        "type", "stepCode", "id", "notifyId", "inputResultId", "bidOpenId", "techReqId",
        "bidPreNotifyResultId", "bidPreOpenId", "processApply", "bidMode", "notifyNo",
        "planNo", "pno", "isInternet", "caseKHKQ", "bidForm",
    )}
    params["step"] = "khlcnt"
    response = client.s.get(url, params=params, timeout=30)
    response.raise_for_status()
    (folder / "detail.html").write_text(response.text, encoding="utf-8")
    detail = client.get_plan_detail(plan["id"])
    for package in detail["bidpPlanDetailToProjectList"]:
        if str(package.get("isMultiLot")) == "0":
            continue
        data = client.get_package_detail(package.get("idDetail") or package["id"])
        (folder / (data["bidNo"] + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print({k: data.get(k) for k in ("bidNo", "bidName", "isMedicine", "baseMedicine", "additionalChoise", "planDecisionDate", "processApply", "bidField", "bidForm", "originalCreateDate")})
        print("LOTS", len(data.get("bidpBidLotList") or []))
        print("FIRST", (data.get("bidpBidLotList") or [None])[0])
source = (folder / "detail.html").read_text(encoding="utf-8")
for name in ():
    match = re.search(r'^\s*' + name + r'\([^\n]*\)\s*\{', source, re.M)
    if match:
        end = re.search(r'^            [\w]+\([^\n]*\)\s*\{', source[match.end():], re.M)
        block = source[match.start():match.end() + end.start()] if end else source[match.start():match.start()+2000]
        print(block)
