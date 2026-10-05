import unittest
from unittest.mock import Mock, patch
from app import ResultRow
from web_app import load_lots_for_download, prepare_lot_download, build_lot_download, NoLotFileError
from lot_analysis import analyze_lots


class ScopeAndAnalysisTests(unittest.TestCase):
    def test_non_multilot_internal_rows_never_export(self):
        for flag in [0, '0', False]:
            client = self.client()
            client.get_package_detail.return_value['isMultiLot'] = flag
            with patch('web_app.MuaSamCongClient', return_value=client), self.assertRaises(NoLotFileError):
                load_lots_for_download(ResultRow(package_id='wanted', package_no='BP2'))

    def test_five_selected_one_without_file_produces_four(self):
        rows = [ResultRow(package_id=str(i), package_no=f'BP{i}', plan_no='2600000001') for i in range(5)]
        rows[4].lot_file_status = 'Ko co file'
        client = self.client()
        client.get_package_detail.side_effect = lambda code: {'bidNo': f'BP{code}', 'isMultiLot': 1,
            'bidpBidLotList': [{'lotNo': f'PP{code}', 'lotName': 'Medicine'}]}
        with patch('web_app.MuaSamCongClient', return_value=client):
            ready, issues = prepare_lot_download(rows, allow_empty=True)
        files, issues = build_lot_download(ready, issues)
        self.assertEqual(len(files), 4)
        self.assertEqual(len(issues), 1)
        self.assertEqual(client.get_package_detail.call_count, 4)
        self.assertEqual([row.lot_file_status for row in rows], ['done']*4+['Ko co file'])

    def test_all_without_files_returns_statuses_and_no_files(self):
        row = ResultRow(package_id='wanted', lot_file_status='Ko co file')
        with patch('web_app.MuaSamCongClient') as factory:
            ready, issues = prepare_lot_download([row], allow_empty=True)
        factory.assert_not_called()
        self.assertEqual(ready, [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(row.lot_file_status, 'Ko co file')

    def client(self):
        client = Mock()
        client.search_plans.return_value = [{'id': 'plan', 'planNo': 'PL2600000001'}]
        client.get_plan_detail.return_value = {'bidpPlanDetailToProjectList': [
            {'idDetail': 'other', 'bidNo': 'BP1', 'bidName': 'Other package'},
            {'idDetail': 'wanted', 'bidNo': 'BP2', 'bidName': 'Selected medicine'},
        ]}
        client.get_package_detail.return_value = {'bidNo': 'BP2', 'bidName': 'Selected medicine',
            'bidpBidLotList': [{'lotNo': 'PP2', 'lotName': 'Medicine'}]}
        return client

    def test_selected_identity_never_fetches_whole_plan_or_other_packages(self):
        client = self.client()
        row = ResultRow(plan_no='2600000001', package_id='wanted', package_no='BP2',
                        package_name='Selected medicine', lot_data=[{'bidNo': 'BP1'}])
        with patch('web_app.MuaSamCongClient', return_value=client):
            actual = load_lots_for_download(row)
        client.get_package_detail.assert_called_once_with('wanted')
        client.get_plan_detail.assert_not_called()
        client.get_plan_lots.assert_not_called()
        self.assertEqual([lot['bidNo'] for lot in actual.lot_data], ['BP2'])
        self.assertEqual(row.lot_data, [{'bidNo': 'BP1'}])

    def test_fast_row_requires_unique_exact_package_name(self):
        client = self.client()
        with patch('web_app.MuaSamCongClient', return_value=client):
            result = load_lots_for_download(ResultRow(plan_no='2600000001', package_name='Selected medicine'))
        self.assertEqual(result.package_no, 'BP2')
        client.get_package_detail.assert_called_once_with('wanted')
        client.get_plan_lots.assert_not_called()

    def test_missing_or_ambiguous_name_does_not_choose_another_package(self):
        client = self.client()
        client.get_plan_detail.return_value['bidpPlanDetailToProjectList'][0]['bidName'] = 'Selected medicine'
        for name in ['Selected medicine', 'Unknown', '']:
            with patch('web_app.MuaSamCongClient', return_value=client), self.assertRaises(ValueError):
                load_lots_for_download(ResultRow(plan_no='2600000001', package_name=name))
        client.get_package_detail.assert_not_called()

    def test_selected_package_without_lots_does_not_fall_back(self):
        client = self.client()
        client.get_package_detail.return_value['bidpBidLotList'] = []
        with patch('web_app.MuaSamCongClient', return_value=client), self.assertRaises(ValueError):
            load_lots_for_download(ResultRow(plan_no='2600000001', package_id='wanted', package_no='BP2'))
        client.get_plan_lots.assert_not_called()

    def lots(self):
        return [{'bidNo': 'BP2', 'lotNo': f'PP{i}', 'lotName': f'Medicine {i}',
                 'medicineCode': f'M{i}', 'quantity': qty, 'pricePlan': price,
                 'uom': 'viên', 'groupMedicine': group,
                 '_export_context': {'isMedicine': 1, 'planDecisionDate': '2026-09-07'}}
                for i, (qty, price, group) in enumerate([(10, 2500, '1'), (20, 1000, '2'), (None, None, '1')], 1)]

    def test_chart_totals_match_export_and_do_not_treat_missing_as_zero(self):
        data = analyze_lots(self.lots(), 'Selected medicine', '2600000001')
        metric = data['metrics'][0]
        self.assertEqual(metric['label'], 'Tổng giá trị (VND)')
        self.assertEqual(metric['total'], '45000')
        self.assertEqual(metric['known'], 2)
        self.assertEqual(metric['missing'], 1)
        self.assertEqual([item['code'] for item in metric['items']], ['PP1', 'PP2'])
        self.assertEqual(sum(group['count'] for group in data['categories']), 3)

    def test_mixed_units_are_not_summed_and_top_ten_does_not_limit_total(self):
        lots = self.lots()[:1] * 12
        lots = [dict(lot, lotNo=f'PP{i}', uom='viên' if i % 2 else 'lọ') for i, lot in enumerate(lots)]
        data = analyze_lots(lots)
        self.assertEqual(len(data['metrics'][0]['items']), 10)
        self.assertEqual(data['metrics'][0]['total'], '300000')
        self.assertFalse(any(metric['label'] == 'Số lượng' for metric in data['metrics']))


if __name__ == '__main__':
    unittest.main()
