import json
from pathlib import Path

from pipeline.sql.executor import ResultWriter, execute_query_plan
from pipeline.sql.schema import QueryPlan, QueryPlanStatus


def test_result_writer_numbers_files(tmp_path: Path):
    writer = ResultWriter(tmp_path)
    first = writer.next_path()
    first.write_text("{}", encoding="utf-8")
    second = writer.next_path()

    assert first.name == "result_0.json"
    assert second.name == "result_1.json"


def test_execute_query_plan_writes_json_result(tmp_path: Path):
    writer = ResultWriter(tmp_path)
    plan = QueryPlan(
        status=QueryPlanStatus.OK,
        sql="SELECT frame_id, datetime, camera_name FROM frames WHERE camera_name = ? ORDER BY datetime LIMIT 1",
        parameters=["Central Expressway (CTE)"],
    )

    result = execute_query_plan(plan, writer=writer)

    payload = json.loads(Path(result.result_file).read_text(encoding="utf-8"))
    assert payload["row_count"] == 1
    assert payload["results"][0]["camera_name"] == "Central Expressway (CTE)"
    assert payload["sql"] == "SELECT frame_id, datetime, camera_name FROM frames WHERE camera_name = 'Central Expressway (CTE)' ORDER BY datetime LIMIT 1"
