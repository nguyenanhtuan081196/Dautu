import ast
from pathlib import Path

import pandas as pd

from simulator import get_historical_return_rate_with_details


ROOT = Path(__file__).resolve().parents[1]


def test_data_jobs_do_not_prompt_or_run_git_commands():
    targets = [
        "fetch_data_local.py",
        "crawl_bctc.py",
        "advanced_screener.py",
        "analyze_ai.py",
        "simulator.py",
    ]
    for relative in targets:
        source = (ROOT / relative).read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        assert "subprocess" not in source, relative
        assert "git push" not in source.lower(), relative
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert not any(node.func.id == "input" for node in calls), relative


def test_simulator_calculates_from_supplied_mongodb_history():
    dates = pd.date_range("2020-01-01", "2026-01-01", freq="30D")
    bars = [
        {"time": date.strftime("%Y-%m-%d"), "close": 100 + index, "volume": 1000}
        for index, date in enumerate(dates)
    ]
    result = get_historical_return_rate_with_details("TEST", bars)
    assert result is not None
    assert result["annual_rate_percent"] > 0
    assert result["start_quarter"].startswith("2021Q")
    assert result["end_quarter"].startswith("2025Q")
