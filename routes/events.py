import azure.functions as func
from db.mongo import get_db
import json

bp = func.Blueprint()

@bp.route(route="events", methods=["GET"])
def get_events(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    events = list(db.Events.find({}, {"_id": 0}))

    return func.HttpResponse(
        body=json.dumps(events),
        mimetype="application/json",
        status_code=200
    )