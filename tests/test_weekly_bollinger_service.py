from datetime import date, timedelta
from io import BytesIO
import unittest

import openpyxl
import pandas as pd

from app.services.weekly_bollinger_service import WeeklyBollingerService


def _weekdays_through(end: date, count: int):
    days, cursor = [], end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


class BollingerRankingTests(unittest.TestCase):
    PERIOD = 5
    AS_OF = date(2026, 11, 20)  # a Friday, so the window is 16-20 Nov 2026
    # Each series has a middle band (mean of its 5 closes) of exactly 100 or 10,000.
    CLOSES = {
        "XSTOCK": [87.5, 87.5, 87.5, 87.5, 150.0],    # middle 100, close 150 -> +50%
        "YSTOCK": [92.5, 92.5, 92.5, 92.5, 130.0],    # middle 100, close 130 -> +30%
        "PRICEY": [9875.0] * 4 + [10500.0],           # middle 10,000, close 10,500 -> +5%
        "BELOW": [102.5, 102.5, 102.5, 102.5, 90.0],  # middle 100, close 90 -> -10%
    }

    def _report(self):
        dates = _weekdays_through(self.AS_OF, self.PERIOD)

        def fake_bhavcopy(session_date):
            index = dates.index(session_date)
            return pd.DataFrame([
                {"TckrSymb": symbol, "SctySrs": "EQ", "TradDt": session_date.isoformat(),
                 "ClsPric": closes[index]}
                for symbol, closes in self.CLOSES.items()
            ])

        universe = [{"symbol": symbol, "company_name": symbol, "series": "EQ"} for symbol in self.CLOSES]
        return WeeklyBollingerService.calculate_universe(
            universe, period=self.PERIOD, as_of=self.AS_OF,
            bhavcopy_fetcher=fake_bhavcopy,
            trading_session_checker=lambda day: day.weekday() < 5,
            max_workers=1,
        )

    def test_ranks_by_percent_above_middle_band(self):
        report = self._report()
        ranked = [(row["rank"], row["symbol"]) for row in report["results"]]
        # PRICEY has by far the highest upper band but only a +5% close.
        self.assertEqual(ranked, [(1, "XSTOCK"), (2, "YSTOCK"), (3, "PRICEY"), (4, "BELOW")])
        percents = {row["symbol"]: row["close_vs_middle_pct"] for row in report["results"]}
        self.assertAlmostEqual(percents["XSTOCK"], 50.0)
        self.assertAlmostEqual(percents["YSTOCK"], 30.0)
        self.assertAlmostEqual(percents["PRICEY"], 5.0)
        self.assertAlmostEqual(percents["BELOW"], -10.0)
        self.assertEqual(report["ranking_basis"], WeeklyBollingerService.RANKING_BASIS)

    def test_reranks_rows_from_older_snapshots(self):
        # Rows saved before the change have no percentage and were ordered by upper band.
        old_rows = [
            {"symbol": "PRICEY", "latest_close": 10500.0, "middle_band": 10000.0, "rank": 1},
            {"symbol": "YSTOCK", "latest_close": 130.0, "middle_band": 100.0, "rank": 2},
            {"symbol": "XSTOCK", "latest_close": 150.0, "middle_band": 100.0, "rank": 3},
        ]
        ranked = WeeklyBollingerService.sort_results(old_rows)
        self.assertEqual([row["symbol"] for row in ranked], ["XSTOCK", "YSTOCK", "PRICEY"])
        self.assertEqual([row["rank"] for row in ranked], [1, 2, 3])

    def test_excel_ranking_sheet_shows_percent_in_rank_order(self):
        excel = WeeklyBollingerService.build_excel_report(self._report())
        workbook = openpyxl.load_workbook(BytesIO(excel["data"]))
        sheet = workbook["Bollinger Ranking"]
        self.assertEqual(sheet.cell(row=1, column=5).value, "% vs Middle Band")
        self.assertEqual([sheet.cell(row=row, column=2).value for row in range(2, 6)],
                         ["XSTOCK", "YSTOCK", "PRICEY", "BELOW"])
        top_percent = sheet.cell(row=2, column=5)
        self.assertAlmostEqual(top_percent.value, 0.5)
        self.assertEqual(top_percent.number_format, "+0.00%;-0.00%;0.00%")


if __name__ == "__main__":
    unittest.main()
