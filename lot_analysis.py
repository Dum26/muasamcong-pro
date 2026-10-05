"""Chart data from the same columns and values used by the e-GP Excel template."""
from collections import Counter
from decimal import Decimal, InvalidOperation
import unicodedata

from lot_export import lot_export_table


def key(value):
    return unicodedata.normalize('NFC', str(value)).casefold().strip()


def number(value, money=False):
    if value is None or value == '':
        return None
    text = str(value).strip()
    if money:
        text = text.replace('.', '').replace(',', '.')
    try:
        result = Decimal(text)
        return result if result.is_finite() and result >= 0 else None
    except InvalidOperation:
        return None


def analyze_lots(lots, package_name='', plan_no=''):
    headers, records = lot_export_table(lots, lots[0]['_export_context'])
    normalized = [key(header) for header in headers]
    codes = next((i for i, header in enumerate(normalized) if header in
                  {'mã phần/lô', 'mã phần (lô)', 'mã phần lô'}), None)
    names = next((i for i, header in enumerate(normalized) if header.startswith('tên ')), None)
    unit_column = next((i for i, h in enumerate(normalized) if h == 'đơn vị tính'), None)
    units = {str(row[unit_column]).strip() or 'Chưa rõ đơn vị' for row in records} if unit_column is not None else set()
    money_fields = {'thành tiền', 'thành tiền (vnd)', 'tổng giá trị (vnd)',
                    'giá ước tính từng lô', 'giá dự toán ước tính từng lô',
                    'giá dự toán ước tính từng lô (vnd)'}
    metrics = []
    for index, header in enumerate(normalized):
        money = header in money_fields
        quantity = header == 'số lượng' and len(units) == 1 and 'Chưa rõ đơn vị' not in units
        if not money and not quantity:
            continue
        items = []
        for row_number, row in enumerate(records, 1):
            value = number(row[index], money=money)
            if value is not None:
                items.append({'code': str(row[codes]) if codes is not None else str(row_number),
                              'name': str(row[names]) if names is not None else '',
                              'value': str(value)})
        items.sort(key=lambda item: Decimal(item['value']), reverse=True)
        metrics.append({'label': headers[index], 'unit': 'VND' if money else next(iter(units)),
                        'total': str(sum((Decimal(item['value']) for item in items), Decimal(0))),
                        'known': len(items), 'missing': len(records) - len(items), 'items': items[:10]})
    metrics.sort(key=lambda metric: (metric['known'] == 0,
                                   not (key(metric['label']).startswith(('thành tiền', 'tổng giá trị')))))
    category_column = next((i for i, header in enumerate(normalized) if header in {'nhóm tckt', 'nhóm thuốc', 'loại thuốc'}), unit_column)
    categories = Counter(str(row[category_column]).strip() or 'Chưa có dữ liệu' for row in records) if category_column is not None else Counter()
    groups = categories.most_common(8)
    if len(categories) > 8:
        groups.append(('Các nhóm còn lại', sum(categories.values()) - sum(count for _, count in groups)))
    return {'package_name': package_name, 'plan_no': plan_no, 'lot_count': len(records),
            'metrics': metrics, 'category_label': headers[category_column] if category_column is not None else '',
            'categories': [{'label': label, 'count': count} for label, count in groups],
            'quantity_note': 'Không cộng số lượng khi khác hoặc thiếu đơn vị tính.' if unit_column is not None and (len(units) != 1 or 'Chưa rõ đơn vị' in units) else '',
            'source': 'Số liệu từ các cột của bảng Danh sách phần/lô xuất Excel; ô trống không được tính là 0.'}
