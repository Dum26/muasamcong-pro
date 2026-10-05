"""Mẫu của nút Xuất Excel / Danh sách phần/lô trên cổng e-GP.

Đối chiếu các hàm exportExcelThuocColo[01062024],
exportExcelBaseMedicine và exportExcelColo ở trang detail-v2 (22/09/2026).
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


EXPORT_CONTEXT_KEYS = (
    "isMedicine", "baseMedicine", "additionalChoise", "planDecisionDate",
    "processApply", "bidField", "bidForm", "originalCreateDate",
)


def currency(value: Any) -> Any:
    if not value:
        return value
    amount = Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    whole, fraction = f"{amount:,.4f}".split(".")
    fraction = fraction.rstrip("0")
    return whole.replace(",", ".") + ("," + fraction if fraction else "")


def lot_export_table(lots: list[dict], context: dict) -> tuple[list[str], list[list[Any]]]:
    """Chọn cùng mẫu/cột với nút xuất trên web; giữ cột trống của mẫu."""
    if not lots:
        raise ValueError("Không có danh sách phần/lô")
    lots = sorted(lots, key=lambda lot: str(lot.get("lotNo") or ""))
    first = lots[0]
    medicine = str(context.get("isMedicine")) == "1"
    medicine_type = str(first.get("medicines"))
    decision = str(context.get("planDecisionDate") or "")[:10]
    created = str(context.get("originalCreateDate") or "")[:10]
    old = not decision or decision < "2024-06-01"
    more_shopping = (
        context.get("processApply") in ("CPTPP", "UKFTA", "EVFTA")
        or (
            context.get("processApply") in ("LDT", "KHAC")
            and decision >= "2024-01-01"
            and not (created >= "2024-10-17" and context.get("bidForm") not in ("DPG", "DTRR"))
        )
    ) and context.get("bidField") in ("HH", "TV", "PTV")
    percentage = more_shopping and decision >= "2025-11-02"
    additional = bool(context.get("additionalChoise"))
    base = medicine and medicine_type == "0" and str(context.get("baseMedicine")) == "1"
    herbs = medicine_type in ("4", "5")
    coded = first.get("medicineCode") is not None
    columns: list[tuple[str, str, str]] = []

    def add(title: str, key: str, kind: str = "value") -> None:
        columns.append((title, key, kind))

    def add_extras() -> None:
        add("Số lượng tùy chọn mua thêm", "quantityAdd", "money")
        if percentage:
            add("Tỷ lệ phần trăm (%)", "percentageAdd", "money")
        add("Giá trị tùy chọn mua thêm", "valueAdd", "money")

    if not medicine:
        add("STT", "", "index")
        add("Mã phần/lô", "lotNo")
        add("Tên phần/lô", "lotName")
        add("Giá ước tính từng lô", "lotPrice", "money_zero")
        if context.get("processApply") in ("LDT", "KHAC"):
            add("Giá dự toán ước tính từng lô", "lotEstimatePrice", "money")
        add("Thời gian thực hiện hợp đồng", "", "period")
    elif base:
        add("STT", "", "index")
        add("Mã phần (lô)", "lotNo")
        add("Tên phần (lô)", "lotName")
        add("Đơn vị tính", "uom")
        add("Số lượng", "quantity")
        add("Đơn giá(VND)", "pricePlan", "money_zero")
        add("Thành tiền (VND)", "", "total_zero")
        add("Thời gian thực hiện hợp đồng", "", "period")
        if additional and percentage:
            add_extras()
        add("Giá dự toán ước tính từng lô (VND)", "lotEstimatePrice", "money")
    elif herbs:
        add("Mã phần lô", "lotNo")
        add("TT", "", "index")
        add("Tên vị thuốc" if medicine_type == "5" else "Tên dược liệu", "lotName")
        add("Nhóm TCKT", "groupMedicine")
        add("Bộ phận dùng", "medicineCode")
        add("Tên khoa học", "tenThuoc")
        add("Dạng sơ chế/ Phương pháp chế biến", "dangBaoChe")
        if not old:
            add("Tiêu chuẩn chất lượng", "qualityStandards")
        add("Đơn vị tính", "uom")
        add("Số lượng", "quantity")
        add("Giá kế hoạch" if old else "Đơn giá (VND)", "pricePlan", "money")
        add("Thành tiền" if old else "Tổng giá trị (VND)", "", "total")
        if not old and additional:
            add_extras()
        add("Giá dự toán ước tính từng lô", "lotEstimatePrice", "money")
    else:
        add("STT", "", "index")
        add("Mã phần/lô", "lotNo")
        if not old and coded:
            add("Mã thuốc", "medicineCode")
        name = {
            "2": "Tên thuốc" if decision < "2025-01-23" else "Tên thành phần của thuốc",
            "6": "Tên vị thuốc cổ truyền", "7": "Tên bán thành phẩm dược liệu",
        }.get(medicine_type, "Tên hoạt chất")
        add("Tên hoạt chất/ Tên thành phần thuốc" if old else name, "lotName")
        if old and coded:
            add("Mã thuốc", "medicineCode")
        if not old and medicine_type != "1":
            add("Nhóm TCKT", "groupMedicine")
        if medicine_type == "1":
            add("Tên thuốc hoặc tương đương điều trị", "tenThuoc")
        if coded:
            add("Nồng độ, hàm lượng" if old else "Nồng độ hoặc hàm lượng", "nongDo")
            add("Đường dùng", "duongDung")
            add("Dạng bào chế", "dangBaoChe")
            add("Đơn vị tính", "uom")
            if old:
                add("Nhóm thuốc", "groupMedicine")
            add("Số lượng", "quantity")
            add("Giá kế hoạch" if old else "Đơn giá (VND)", "pricePlan", "money")
            add("Thành tiền" if old else "Tổng giá trị (VND)", "", "total")
        if not old and additional:
            add_extras()
        add("Giá dự toán ước tính từng lô", "lotEstimatePrice", "money")
        if not coded:
            add("Giá ước tính từng lô", "lotPrice", "money")
            add("Thời gian thực hiện hợp đồng", "", "raw_period")
            add("Loại thuốc", "medicines", "medicine_type")

    records = []
    units = {"D": "ngày", "T": "tháng", "M": "tháng", "Q": "quý", "N": "năm", "Y": "năm", "W": "tuần"}
    for index, lot in enumerate(lots, 1):
        values = []
        for _, key, kind in columns:
            value = lot.get(key)
            if kind == "index":
                value = index
            elif kind in ("money", "money_zero"):
                value = currency(value) if value or kind == "money_zero" else ""
            elif kind in ("total", "total_zero"):
                quantity, price = lot.get("quantity"), lot.get("pricePlan")
                value = currency(float(quantity or 0) * float(price or 0)) if (quantity and price) or kind == "total_zero" else ""
            elif kind in ("period", "raw_period"):
                unit = lot.get("cperiodUnit")
                unit = units.get(str(unit), "") if kind == "period" else (unit or "")
                value = f"{lot.get('cperiod', '')} {unit}"
            elif kind == "medicine_type":
                value = {"0": "Thuốc Generic", "1": "Thuốc biệt dược", "2": "Thuốc cổ truyền"}.get(str(value), "")
            else:
                value = value or ""
            values.append(value)
        records.append(values)
    return [title for title, _, _ in columns], records
