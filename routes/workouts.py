import os, logging
import azure.functions as func
import jwt
from db.mongo import get_db
import json
from decorators import jwt_required
from bson import ObjectId
from bson.errors import InvalidId

bp = func.Blueprint()

#helper to decode JWT token
def decodeToken(token):
    decoded = jwt.decode(
        token,
        os.environ.get("JWT_SECRET_KEY"),
        algorithms=["HS256"]
    )
    return decoded.get("userId")

@bp.route(route="v1.0/deleteWorkout/{id}", methods=["DELETE", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def delete_workout(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("deleteWorkout called")

    #connecting to MongoDB
    db = get_db()
    events = db.Events
    workoutLogs = db.workoutLogs

    #checking for id and making sure it is valid
    id = req.route_params.get("id")
    if not id:
        return func.HttpResponse(
            json.dumps({"error": "workoutLogId missing"}),
            mimetype="application/json",
            status_code=400
        )

    try:
        workoutLogId = ObjectId(id)
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid workoutLogId"}),
            mimetype="application/json",
            status_code=400
        )
    
    #get token from request, set by decorator
    token = getattr(req, "jwt_token", None)

    #obtain userId from JWT
    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )

    #deleting specified document from mongoDB
    result = workoutLogs.delete_one({"_id": workoutLogId, "userId": user_id})

    eventResult = events.update_one(
        {"workoutLogId": workoutLogId, "userId": user_id},
        {"$set": {"workoutLogId": None, "eventType": "STANDARD"}}
    )

    logging.info('deleted count: '+str(result.deleted_count))
    logging.info('matched count: '+str(eventResult.matched_count))

    if result.deleted_count == 1:
        if eventResult.matched_count == 1:
            return func.HttpResponse(
                status_code=204
            )
    
    return func.HttpResponse(
        json.dumps({"error": "Forbidden or workout log not found"}),
        mimetype="application/json",
        status_code=403
    )


@bp.route(route="v1.0/editWorkout/{id}", methods=["PATCH", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def edit_workout(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("editWorkout called")

    #connecting to MongoDB
    db = get_db()
    workoutLogs = db.workoutLogs
    exercises = db.exercises

    #checking for id and making sure it is valid
    id = req.route_params.get("id")
    if not id:
        return func.HttpResponse(
            json.dumps({"error": "workoutLogId missing"}),
            mimetype="application/json",
            status_code=400
        )

    try:
        workoutLogId = ObjectId(id)
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid workoutLogId"}),
            mimetype="application/json",
            status_code=400
        )
    
    #get token from request, set by decorator
    token = getattr(req, "jwt_token", None)

    #obtain userId from JWT
    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )
    
    workoutLog = workoutLogs.find_one({"_id": workoutLogId, "userId": user_id})
    if not workoutLog:
        return func.HttpResponse(
            json.dumps({"error": "Workout log not found"}),
            mimetype="application/json",
            status_code=404
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
    
    allowedFields = {'exercises', 'notes'}

    #checking for invalid fields in JSON
    invalidFields = [field for field in data if field not in allowedFields]
    if invalidFields:
        return func.HttpResponse(
            json.dumps({"error": "Invalid fields submitted", "invalid": invalidFields}),
            mimetype="application/json",
            status_code=400
        )
    
    # empty payload object, fields added after validation
    workout_payload = {}

    # validating notes value
    if "notes" in data:
        notes = data["notes"]
        
        if notes is None:
            workout_payload["notes"] = None

        elif isinstance(notes, str):
            notesTrimmed = notes.strip()

            if len(notesTrimmed) > 2000:
                return func.HttpResponse(
                    json.dumps({"error": "'notes' is too long. Maximum 2000 characters"}),
                    mimetype="application/json",
                    status_code=400
                )
            if notesTrimmed:
                workout_payload["notes"] = notesTrimmed
            else:
                workout_payload["notes"] = None

        else:
            return func.HttpResponse(
                json.dumps({"error": "'notes' is invalid. Must be non empty string or null"}),
                mimetype="application/json",
                status_code=400
            )
        
    # validating exercises list
    if "exercises" not in data:
        return func.HttpResponse(
            json.dumps({"error": "missing exercises"}),
            mimetype="application/json",
            status_code=400
        )
    
    exercises_payload = data["exercises"]

    if not isinstance(exercises_payload, list):
        return func.HttpResponse(
            json.dumps({"error": "'exercises' must be a list"}),
            mimetype="application/json",
            status_code=400
        )
    
    if len(exercises_payload) == 0:
        return func.HttpResponse(
            json.dumps({"error": "'exercises' cannot be empty"}),
            mimetype="application/json",
            status_code=400
        )
    
    errors = []
    validated_exercises = []

    for exercise_index, exercise in enumerate(exercises_payload):

        if not isinstance(exercise, dict):
            errors.append({f"exercises[{exercise_index}]": "must be an object"})
            continue

        if "exerciseId" not in exercise:
            errors.append({f"exercises[{exercise_index}]": "missing exerciseId"})
            continue

        if "sets" not in exercise:
            errors.append({f"exercises[{exercise_index}]": "missing sets"})
            continue

        try:
            exerciseId = ObjectId(exercise["exerciseId"])
        except (InvalidId, TypeError):
            errors.append({f"exercises[{exercise_index}]": "invalid exerciseId"})
            continue

        existing = exercises.find_one({"_id": exerciseId})
        if existing is None:
            errors.append({f"exercises[{exercise_index}]": "exerciseId does not exist"})
            continue
        else:
            exerciseName = existing["name"]

        sets = exercise["sets"]

        if not isinstance(sets, list):
            errors.append({f"exercises[{exercise_index}]": "sets must be a list"})
            continue

        if len(sets) == 0:
            errors.append({f"exercises[{exercise_index}]": "sets cannot be empty"})
            continue

        validated_sets = []
        all_sets_valid = True

        for set_index, workout_set in enumerate(sets):

            if not isinstance(workout_set, dict):
                errors.append({f"exercises[{exercise_index}].sets[{set_index}]": "must be an object"})
                all_sets_valid = False
                continue

            if "reps" not in workout_set:
                errors.append({f"exercises[{exercise_index}].sets[{set_index}]": "missing reps"})
                all_sets_valid = False
                continue

            reps = workout_set["reps"]

            if isinstance(reps, bool) or not isinstance(reps, int) or reps <=0:
                errors.append({f"exercises[{exercise_index}].sets[{set_index}].reps": "must be an integer > 0"})
                all_sets_valid = False
                continue

            if "weight" not in workout_set:
                errors.append({f"exercises[{exercise_index}].sets[{set_index}]": "missing weight"})
                all_sets_valid = False
                continue

            weight = workout_set["weight"]

            if isinstance(weight, bool) or not isinstance(weight, (int, float)) or weight <0:
                errors.append({f"exercises[{exercise_index}].sets[{set_index}].weight": "must be a number >= 0"})
                all_sets_valid = False
                continue

            validated_sets.append({
                "reps": reps,
                "weight": float(weight)
            })

        if not all_sets_valid:
            continue

        validated_exercises.append({
            "exerciseId": exerciseId,
            "name": exerciseName,
            "sets": validated_sets
        })

    if errors:
        return func.HttpResponse(
            json.dumps({"error": "Invalid data", "details": errors}),
            mimetype="application/json",
            status_code=400
        )

    workout_payload["exercises"] = validated_exercises

    update_result = workoutLogs.update_one(
        {"_id": workoutLogId, "userId": user_id},
        {"$set": workout_payload}
    )

    if update_result.matched_count == 0:
        return func.HttpResponse(
            json.dumps({"error": "Workout log not found or forbidden"}),
            mimetype="application/json",
            status_code=404
        )
    
    return func.HttpResponse(status_code=204)


@bp.route(route="v1.0/workouts/{id}", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_workout(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("editWorkout called")

    #connecting to MongoDB
    db = get_db()
    workoutLogs = db.workoutLogs

    #checking for id and making sure it is valid
    id = req.route_params.get("id")
    if not id:
        return func.HttpResponse(
            json.dumps({"error": "workoutLogId missing"}),
            mimetype="application/json",
            status_code=400
        )

    try:
        workoutLogId = ObjectId(id)
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid workoutLogId"}),
            mimetype="application/json",
            status_code=400
        )
    
    #get token from request, set by decorator
    token = getattr(req, "jwt_token", None)

    #obtain userId from JWT
    try:
        user_id = ObjectId(decodeToken(token))
    except (InvalidId, TypeError):
        return func.HttpResponse(
            json.dumps({"error": "Invalid userId in token"}),
            mimetype="application/json",
            status_code=401
        )
    
    workoutLog = workoutLogs.find_one({"_id": workoutLogId, "userId": user_id})
    if not workoutLog:
        return func.HttpResponse(
            json.dumps({"error": "Workout log not found"}),
            mimetype="application/json",
            status_code=404
        )
    
    workoutLog["_id"] = str(workoutLog["_id"])
    workoutLog["userId"] = str(workoutLog["userId"])
    workoutLog["eventId"] = str(workoutLog["eventId"])
    workoutLog["date"] = workoutLog["date"].isoformat()
    for exercise in workoutLog.get("exercises", []):
        exercise["exerciseId"] = str(exercise["exerciseId"])

    return func.HttpResponse(
        body=json.dumps(workoutLog),
        mimetype="application/json",
        status_code=200
    )