import azure.functions as func
from db.mongo import get_db
import json
from decorators import jwt_required
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime

bp = func.Blueprint()

eventTypes = ["STANDARD", "WORKOUT"]

#helper method to check string inputs
def checkString(value):
    if isinstance(value, str) and value.strip():
        return True
    else:
        return False
    
#helper method to check datetime inputs
def checkDatetime(value):
    if not checkString(value):
        return False
    
    try:
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return False

@bp.route(route="events", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
#endpoint to test initial setup of MongoDB and deploy to azure. NOT USED IN PROD
def get_events(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    events = list(db.Events.find({}, {"_id": 0}))

    return func.HttpResponse(
        body=json.dumps(events),
        mimetype="application/json",
        status_code=200
    )


@bp.route(route="userEvents", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_user_events(req: func.HttpRequest) -> func.HttpResponse:
    #connecting to MongoDB
    db = get_db()

    #checking for valid userId
    try:
        user_id = ObjectId(req.params.get("userId"))
    except InvalidId:
        return func.HttpResponse(
            json.dumps({'error': 'userId is invalid'}),
            mimetype="application/json",
            status_code=400
        )

    if not user_id:
        return func.HttpResponse(
            json.dumps({'error': 'userId is missing'}),
            mimetype="application/json",
            status_code=400
        )

    events = list(db.Events.find({'userId': user_id}))

    for event in events:
        event['_id'] = str(event['_id'])
        event['userId'] = str(event['userId'])
        event['workoutLogId'] = str(event['workoutLogId'])

    return func.HttpResponse(
        body=json.dumps(events),
        mimetype="application/json",
        status_code=200
    )



@bp.route(route="createEvent", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def create_event(req: func.HttpRequest) -> func.HttpResponse:
    #connecting to MongoDB
    db = get_db()
    users = db.users
    
    #checking for valid JSON body in request
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking required fields are present
    required = ["userId", "eventType", "title", "start", "end"]
    missing = [field for field in required if field not in data]
    if missing:
        return func.HttpResponse(
            json.dumps({"error": "Missing data", "missing": missing}),
            mimetype="application/json",
            status_code=400
        )
    
    #validating required fields
    invalid_fields = []
    if checkString(data["userId"]):
        try:
            event_userId = ObjectId(data["userId"].strip())
        except (InvalidId, TypeError, AttributeError):
            invalid_fields.append("userId")
    else:
        invalid_fields.append("userId")
    if checkString(data["title"]):
        event_title = data["title"].strip()
    else:
        invalid_fields.append("title")
    if checkString(data["eventType"]) and data["eventType"].strip() in eventTypes:
        event_type = data["eventType"].strip()
    else:
        invalid_fields.append("eventType")
    event_start = checkDatetime(data["start"])
    if not event_start:
        invalid_fields.append("start")
    event_end = checkDatetime(data["end"])
    if not event_end:
        invalid_fields.append("end")
    
    if invalid_fields:
        return func.HttpResponse(
            json.dumps({"error": "Invalid data", "invalid": invalid_fields}),
            mimetype="application/json",
            status_code=400
        )
    
    if event_end <= event_start:
        return func.HttpResponse(
            json.dumps({"error": "event end must be after start"}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking optional fields and setting to None if not present
    event_description = data.get("description")
    if checkString(event_description):
        event_description = event_description.strip()
    else:
        event_description = None
    event_location = data.get("location")
    if checkString(event_location):
        event_location = event_location.strip()
    else:
        event_location = None
    event_workout_id = data.get("workoutLogId")
    if checkString(event_workout_id):
        #checking workoutLogId is valid oid
        try:
            event_workout_id = ObjectId(event_workout_id.strip())
        except (InvalidId, TypeError):
            return func.HttpResponse(
                json.dumps({'error': 'workoutLogId is invalid'}),
                mimetype="application/json",
                status_code=400
            )
    else:
        event_workout_id = None
    
    #checking userId exists
    existing = users.find_one({"_id": event_userId})
    if not existing:
        return func.HttpResponse(
            json.dumps({"error": "userId does not exist"}),
            mimetype="application/json",
            status_code=409
        )
    
    #creating new event object
    new_event = {
        'userId': event_userId,
        'eventType': event_type,
        'title': event_title,
        'description': event_description,
        'start': event_start,
        'end': event_end,
        'location': event_location,
        'workoutLogId': event_workout_id
    }

    #inserting new event in MongoDB
    result = db.Events.insert_one(new_event)

    #create link for new created event?
    #response with newly created event ID
    return func.HttpResponse(
            json.dumps({"message": "Event created", "id": str(result.inserted_id)}),
            mimetype="application/json",
            status_code=201
        )