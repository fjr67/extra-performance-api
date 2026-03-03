import json
import azure.functions as func
import re

from bson import ObjectId
from db.mongo import get_db
from decorators import jwt_required

bp = func.Blueprint()

@bp.route(route="v1.0/exercises", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_exercises(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    exercises = db.exercises

    if req.params.get('pn'):
        try:
            page_num = int(req.params.get('pn'))
        except TypeError:
            return func.HttpResponse(
                json.dumps({'error':'pn must be integer'}),
                mimetype="application/json",
                status_code=400
            )

    else:
        return func.HttpResponse(
            json.dumps({'error':'missing pn'}),
            mimetype="application/json",
            status_code=400
        )
    
    if req.params.get('ps'):
        try:
            page_size = int(req.params.get('ps'))
        except TypeError:
            return func.HttpResponse(
                json.dumps({'error':'ps must be integer'}),
                mimetype="application/json",
                status_code=400
            )

    else:
        return func.HttpResponse(
            json.dumps({'error':'missing ps'}),
            mimetype="application/json",
            status_code=400
        )
    
    page_start = (page_size * (page_num - 1))

    query = {}

    primaryMuscle = req.params.get("primaryMuscle")
    if primaryMuscle and primaryMuscle != 'ALL':
        query["primaryMuscle"] = primaryMuscle

    search = req.params.get("search")
    if search:
        query["name"] = {'$regex': re.escape(search), '$options': 'i'}

    excludeIds = req.params.get('excludeIds')
    if excludeIds:
        id_list = excludeIds.split(',')
        objectIds = [ObjectId(id) for id in id_list]
        query["_id"] = {"$nin": objectIds}

    exercises_to_return = []
    for exercise in exercises.find(query).sort("name", 1).skip(page_start).limit(page_size):
        exercise["_id"] = str(exercise["_id"])
        exercises_to_return.append(exercise)

    total_exercises = exercises.count_documents(query)
    response_body = {
        "exercises": exercises_to_return,
        "page": page_num,
        "pageSize": page_size,
        "totalExercises": total_exercises
    }

    return func.HttpResponse(
        body=json.dumps(response_body),
        mimetype="application/json",
        status_code=200
    )


@bp.route(route="v1.0/exercises/primaryMuscles", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
@jwt_required
def get_primaryMuscles(req: func.HttpRequest) -> func.HttpResponse:
    db = get_db()
    exercises = db.exercises

    primaryMuscles = exercises.distinct("primaryMuscle")
    primaryMuscles.sort()

    return func.HttpResponse(
        body=json.dumps(primaryMuscles),
        mimetype="application/json",
        status_code=200
    )