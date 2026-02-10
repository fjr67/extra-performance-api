# Copilot Instructions for extra-performance-api

## Project Vision
**ExtraPerformance** is a unified web application combining calendar scheduling with workout logging. Users can manage daily commitments and fitness routines in one place, addressing the fragmentation of using separate calendar and workout tracking apps. The system tracks performance metrics, provides analytics, and supports both gym (strength) and cardio workouts.

**Scope (by delivery date 23-Apr-2026):**
- User authentication and account management
- Calendar with daily/weekly/monthly views and CRUD operations
- Workout event creation linked to calendar
- Gym workout logging (exercises, sets, reps, weights) and cardio logging (distance, time)
- Progress tracking with goals and personal records
- Notifications/reminders via email (Amazon SES)

**Out of scope:** Mobile app, nutrition tracking, third-party integrations, social features, wearables.

**Tech Stack:** Azure Functions (Python), MongoDB, bcrypt for authentication, email via Amazon SES

## Architecture

### Core Structure
- **`function_app.py`** - Main entry point using Azure Functions v2. Registers blueprints from `routes/`. Uses `AuthLevel.FUNCTION` for HTTP auth.
- **`routes/`** - HTTP endpoints organized by domain (users.py, events.py, workouts.py). Each exports `bp = func.Blueprint()` registered in function_app.py.
- **`db/mongo.py`** - MongoDB singleton with lazy initialization. Always call `get_db()` for "ExtraPerformanceDB" access.

### Database Collections
- **`users`** - Fields: `_id`, `name`, `username`, `email`, `password` (bcrypt-hashed)
- **`Events`** - Fields: `_id`, `userId`, `eventType` (standard|workout), `title`, `description`, `start`, `end`, `location`, `workoutLogId`
- **`workoutLogs`** - Hierarchical: gym sessions (exercises array with sets/reps/weights) or cardio (distance, time, cardioType)
- **`goals`** - User-defined performance targets
- **`personalRecords`** - Gym: `exerciseId`, `userId`, `weight`, `reps`, `dateAchieved` | Cardio: `cardioType`, `userId`, `distance`, `time`, `dateAchieved`
- **`exercises`** - Gym exercise library: `_id`, `name`, `muscleGroup`

## Feature Prioritization (MoSCoW)

### Must Have (Core MVP)
**User Management:** Register, login, logout, view account, delete account  
**Calendar Events:** Create/edit/delete/view events, daily/weekly views, store/retrieve event data  
**Workout Events:** Create/edit/delete workout events, link to calendar  
**Workout Logging:** Log gym sessions (exercises+sets/reps/weights) and cardio sessions (distance+time), view logs  
**Goals & Progress:** Create goals, view progress  
**Data Operations:** All CRUD operations for users, events, workouts (FR-56 through FR-61)  
**Security:** HTTPS, secure password hashing, error handling without data loss, GDPR compliance  
**UI/Navigation:** Intuitive interface, responsive design, navigation between dashboard/calendar/workouts

### Should Have (High Priority)
Change password, reset password, view account details, workout type specification, recurring events (create/edit/delete), edit/delete workouts, personal records (gym), notes on workouts, color coding events, reminders/notifications (single), dashboard views (upcoming events, performance/progress), weekly workout count

### Could Have (Nice-to-Have)
Google login, two-factor auth, monthly view, search/filter events, attach templates, duplicate workouts, gym templates, multiple reminders, cardio logging, cardio personal records, volume/totals tracking, trend graphs

### Won't Have (Out of Scope)
Meal events/logging, Google Calendar integration, third-party integrations

## Key Patterns & Conventions

### Blueprint Routing
All HTTP endpoints are defined as functions within blueprint files. Register new routes by:
1. Creating a function decorated with `@bp.route(route="endpoint", methods=["GET"|"POST"|...])`
2. Exporting `bp = func.Blueprint()` at module level
3. Importing and registering in `function_app.py` via `app.register_blueprint()`

**Example from users.py:**
```python
@bp.route(route="register", methods=["POST"])
def registerAccount(req: func.HttpRequest) -> func.HttpResponse:
    data = req.get_json()  # Parse JSON body
    # ... validation and DB operations ...
    return func.HttpResponse(
        json.dumps({"message": "..."}),
        mimetype="application/json",
        status_code=201
    )
```

### Response Format
Always return `func.HttpResponse` with:
- `body` - JSON string via `json.dumps(dict)`
- `mimetype="application/json"`
- `status_code` - Use 201 for creation, 400 for bad requests, 409 for conflicts, 200 for success

### Data Validation
Validate request bodies before database operations:
1. Try `req.get_json()` wrapped in try/except for JSON parsing errors
2. Check for required fields using list comprehension: `missing = [k for k in required if k not in data]`
3. Type-check critical fields (e.g., password must be string before hashing)

### Password Security
Use **bcrypt** (already in requirements.txt):
- Hash: `bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")`
- Verify: `bcrypt.checkpw(provided.encode("utf-8"), stored.encode("utf-8"))`

### Database Access
Always use the singleton pattern:
```python
from db.mongo import get_db
db = get_db()  # Returns ExtraPerformanceDB
users_collection = db.users  # Access collections directly
```

The connection is initialized only once (lazy) and verified with a ping command on first access to fail fast on misconfiguration.

## Development Workflow

### Start the Local Function Host
```
func start
```
This starts the Azure Functions runtime locally at http://localhost:7071. Endpoints are available at `http://localhost:7071/api/{route}`.

### Dependencies
Run `pip install -r requirements.txt` before first start. Required packages:
- `azure-functions` - Azure Functions runtime
- `pymongo[srv]` - MongoDB with SRV connection support
- `bcrypt` - Password hashing

## Integration Points

### MongoDB Connection
Connection URI is sourced from `MONGODB_URI` environment variable (configured in `local.settings.json` for development). The connection happens on first `get_db()` call, not on module import.

### Azure Functions Runtime
- Configured in `host.json` with extension bundle v4
- Application Insights logging is enabled
- Functions require valid HTTP requests with proper JSON bodies

## Critical Project Risks & Mitigations

**Top Risks Identified:**
1. **Security vulnerabilities (Risk Level: 15)** - Mitigation: Use bcrypt hashing, validate all user input, HTTPS-only comms, follow OWASP guidelines
2. **New/changing requirements (Risk Level: 15)** - Mitigation: Use iterative development with MoSCoW prioritization; prioritize Must/Should features first
3. **Project deadline pressure (Risk Level: 12)** - Mitigation: Deliver Must features first per schedule, defer Could/Won't features if needed
4. **Database failure (Risk Level: 10)** - Mitigation: Regular MongoDB backups, validate schema on data access
5. **Underestimating feature complexity (Risk Level: 9)** - Mitigation: Break large features into subtasks, prototype high-complexity items early
6. **Unfamiliar technology (Risk Level: 6)** - Mitigation: Document patterns as you discover them, reference Azure Functions and pymongo docs liberally

## Architectural Decisions & Why

**MongoDB over SQL:** Hierarchical workout data (workouts → exercises → sets) maps naturally to JSON documents. No complex joins needed for retrieving full workout context. Schema-less design accommodates requirement changes.

**Azure Functions over traditional server:** Serverless reduces ops burden for single developer, automatic scaling, pay-per-execution model suits variable traffic.

**Blueprint-based routing:** Organizes endpoints by domain (users, events, workouts), making it easy to add new routes and scale the codebase.

**Singleton MongoDB connection:** Reduces connection overhead, ensures consistent database access pattern across all endpoints.

## When Adding New Features

1. **New Endpoint**: Create route in `routes/{domain}.py` (create new file if needed), register blueprint in `function_app.py`
2. **New Collection**: Define schema expectations clearly in comments. Access via `get_db().{collection_name}`. Ensure case sensitivity matches existing conventions.
3. **Workout-related features**: Remember gym and cardio have different data structures. Gym = hierarchical (exercises array with sets/reps/weights), Cardio = flat (distance, time, cardioType)
4. **Authentication**: Extend user-specific auth by adding bearer token validation in endpoints (not yet implemented). Check `userId` in request against token.
5. **Email notifications**: Use Amazon SES for reminders (FR-51). Implement in notification service pattern per architecture.
6. **Testing locally**: Use `func start` to run locally at http://localhost:7071/api/{route}. Test with curl, Postman, or VS Code REST Client extension.

## Critical Gotchas

- **Collections are case-sensitive in MongoDB**: `db.Events` ≠ `db.events`. Maintain consistency with existing collection names.
- **MongoDB connection fails silently** if `MONGODB_URI` is missing—configure it in `local.settings.json` before running.
- **Blueprint registration order** in `function_app.py` doesn't affect routing, but organize for readability.
- **JSON responses** must be strings (not dict objects)—always use `json.dumps()`.
- **Gym vs Cardio data structures differ significantly**: Gym workouts are hierarchical (exercises contain sets), cardio workouts are flat. Check `workoutType` field before accessing data.
- **User data isolation**: All queries should filter by `userId` to prevent cross-user data leakage. This is **critical** for GDPR/security.
- **Recurring events are not yet implemented** (FR-25-28) - these are Should/Could priority and require calendar service enhancement.
- **Amazon SES integration** (FR-01, FR-51) needs AWS credentials in environment. Not configured in current setup—add when implementing account validation/reminders.
- **GDPR compliance requirement** (NFR-11): Implement data deletion cascades (delete user → delete all events/workouts/goals/records). Account deletion (FR-07) must be atomic.
