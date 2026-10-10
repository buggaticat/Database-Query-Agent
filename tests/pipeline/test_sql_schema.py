from pipeline.sql.schema import QueryPlan, QueryPlanStatus, QueryPredicate


def test_query_plan_shape():
    plan = QueryPlan(
        status=QueryPlanStatus.OK,
        sql="SELECT frame_id, datetime, camera_name FROM frames WHERE camera_name = ?",
        parameters=["Central Expressway (CTE)"],
        predicates=[QueryPredicate(field="camera_name", operator="eq", value="CTE")],
    )

    assert plan.status == QueryPlanStatus.OK
    assert plan.parameters == ["Central Expressway (CTE)"]

