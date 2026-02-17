import os, logging
import azure.functions as func
from db.mongo import get_db
import json
from decorators import jwt_required
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
import jwt

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
    
    #making datetime valid for python
    try:
        value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return False
    
#helper to decode JWT token
def decodeToken(token):
    decoded = jwt.decode(
        token,
        os.environ.get("JWT_SECRET_KEY"),
        algorithms=["HS256"]
    )
    return decoded.get("userId")

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


@bp.route(route="v1.0/userEvents", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def get_user_events(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("userEvents called")

    #connecting to MongoDB
    db = get_db()

    #getting userId from token and validating
    try:
        user_id = ObjectId(decodeToken(req.headers.get("x-access-token")))
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
    
    #getting from and to parameters from request
    fromParam = req.params.get("from")
    toParam = req.params.get("to")

    #checking parameters are present
    if not fromParam or not toParam:
        return func.HttpResponse(
            json.dumps({'error': "'from' and 'to' are required parameters"}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking parameters are valid
    invalid_fields = []
    from_dt = checkDatetime(fromParam)
    if not from_dt:
        invalid_fields.append('from')
    to_dt = checkDatetime(toParam)
    if not to_dt:
        invalid_fields.append('to')
    
    if invalid_fields:
        return func.HttpResponse(
            json.dumps({"error": "Invalid data", "invalid": invalid_fields}),
            mimetype="application/json",
            status_code=400
        )
    
    if to_dt <= from_dt:
        return func.HttpResponse(
            json.dumps({"error": "'to' must be after 'from'"}),
            mimetype="application/json",
            status_code=400
        )

    #querying db for user events
    events = list(db.Events.find({
        'userId': user_id,
        "start": {"$lt": to_dt},
        "end": {"$gt": from_dt} 
        }).sort("start", 1))

    #converting non-string values to string for output
    for event in events:
        event['_id'] = str(event['_id'])
        event['userId'] = str(event['userId'])
        if event['workoutLogId']:
            event['workoutLogId'] = str(event['workoutLogId'])
        event['start'] = str(event['start'])
        event['end'] = str(event['end'])

    #returning list of events
    return func.HttpResponse(
        body=json.dumps(events),
        mimetype="application/json",
        status_code=200
    )



@bp.route(route="v1.0/createEvent", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def create_event(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("createEvent called")

    #connecting to MongoDB
    db = get_db()
    users = db.users
    events = db.Events
    
    #checking for valid JSON body in request
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not isinstance(data, dict):
        return func.HttpResponse(
            json.dumps({"error": "Request body must be a valid JSON object"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not data:
        return func.HttpResponse(
            json.dumps({"error": "Request body cannot be empty"}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking required fields are present
    required = {"eventType", "title", "start", "end"}
    missing = [field for field in required if field not in data]
    if missing:
        return func.HttpResponse(
            json.dumps({"error": "Missing data", "missing": missing}),
            mimetype="application/json",
            status_code=400
        )
    
    #getting userId from token
    userId = decodeToken(req.headers.get("x-access-token"))
    
    #validating required fields
    invalid_fields = []
    try:
        event_userId = ObjectId(userId)
    except (InvalidId, TypeError, AttributeError):
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
            status_code=403
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
    result = events.insert_one(new_event)

    #create link for new created event?
    #response with newly created event ID
    return func.HttpResponse(
            json.dumps({"message": "Event created", "id": str(result.inserted_id)}),
            mimetype="application/json",
            status_code=201
        )


@bp.route(route="v1.0/editEvent/{id}", methods=["PATCH"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def edit_event(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("editEvent called")

    #connecting to MongoDB
    db = get_db()
    events = db.Events

    #checking for id and making sure it is valid
    id = req.route_params.get("id")
    if not id:
        return func.HttpResponse(
            json.dumps({"error": "eventId missing"}),
            mimetype="application/json",
            status_code=400
        )

    try:
        eventId = ObjectId(id)
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid eventId"}),
            mimetype="application/json",
            status_code=400
        )
    
    #checking for valid JSON body in request
    try:
        data = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "Request body must be valid JSON"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not isinstance(data, dict):
        return func.HttpResponse(
            json.dumps({"error": "Request body must be a valid JSON object"}),
            mimetype="application/json",
            status_code=400
        )
    
    if not data:
        return func.HttpResponse(
            json.dumps({"error": "Request body cannot be empty"}),
            mimetype="application/json",
            status_code=400
        )
    
    #retieve userId from JWT
    try:
        user_id = ObjectId(decodeToken(req.headers.get("x-access-token")))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    allowedFields = {'eventType', 'title', 'description', 'start', 'end', 'location', 'workoutLogId'}

    #checking for invalid fields in JSON
    invalidFields = [field for field in data if field not in allowedFields]
    if invalidFields:
        return func.HttpResponse(
            json.dumps({"error": "Invalid fields submitted", "invalid": invalidFields}),
            mimetype="application/json",
            status_code=400
        )
    
    #categorising fields so appropriate validation can be applied
    requiredStringFields = {'eventType', 'title'}
    dateFields = {'start', 'end'}
    optionalFields = {'description', 'location'}

    edited_event = {}
    errors = {}

    for field, value in data.items():
        if field in requiredStringFields:
            if checkString(value):
                edited_event[field] = value.strip()
            else:
                errors[field] = "Invalid string"
        elif field in dateFields:
            edited_event[field] = checkDatetime(value)
            if not edited_event[field]:
                errors[field] = "Invalid date"
        elif field in optionalFields:
            if checkString(value):
                edited_event[field] = value.strip()
            elif value is None:
                edited_event[field] = None
            else:
                errors[field] = "Invalid string"
        elif field == 'workoutLogId':
            if value is None:
                edited_event['workoutLogId'] = None
            else:
                errors['workoutLogId'] = "workoutLogId cannot be edited, can only be set to null"

    #returning 400 with errors if any are present
    if errors:
        return func.HttpResponse(
            json.dumps({"error": "Invalid fields submitted", "invalid": errors}),
            mimetype="application/json",
            status_code=400
        )
    
    if not edited_event:
        return func.HttpResponse(
            json.dumps({"error": "No fields to be edited"}),
            mimetype="application/json",
            status_code=400
        )
    
    #updating mongoDB document with updated fields
    result = events.update_one(
        {"_id": eventId, "userId": user_id},
        {"$set": edited_event}
    )

    if result.modified_count == 0:
        return func.HttpResponse(
            status_code=204
        )
    
    if result.matched_count == 1:
        return func.HttpResponse(
            json.dumps({"success": "event updated successfully"}),
            mimetype="application/json",
            status_code=200
        )
    else:
        return func.HttpResponse(
            json.dumps({"error": "Forbidden or event not found"}),
            mimetype="application/json",
            status_code=403
        )
    

@bp.route(route="v1.0/deleteEvent/{id}", methods=["DELETE"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def delete_event(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("deleteEvent called")

    #connecting to MongoDB
    db = get_db()
    events = db.Events

    #checking for id and making sure it is valid
    id = req.route_params.get("id")
    if not id:
        return func.HttpResponse(
            json.dumps({"error": "eventId missing"}),
            mimetype="application/json",
            status_code=400
        )

    try:
        eventId = ObjectId(id)
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid eventId"}),
            mimetype="application/json",
            status_code=400
        )
    
    #obtain userId from JWT
    try:
        user_id = ObjectId(decodeToken(req.headers.get("x-access-token")))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    #deleting specified document from mongoDB
    result = events.delete_one({"_id": eventId, "userId": user_id})

    if result.deleted_count == 1:
        return func.HttpResponse(
            status_code=204
        )
    else:
        return func.HttpResponse(
            json.dumps({"error": "Forbidden or event not found"}),
            mimetype="application/json",
            status_code=403
        )