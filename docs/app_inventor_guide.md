# DaySync AI MVP — MIT App Inventor Integration Guide

This guide describes how to build the Android frontend for **DaySync AI MVP** in MIT App Inventor. The backend returns flat JSON lists and one-level objects so App Inventor can decode responses using the Web component and the built-in JSON blocks.

Set a global variable named `SERVER_URL`, for example `http://YOUR_SERVER_IP:8000`. Add one TinyDB component to every screen that needs authentication and store the JWT token under the tag `token` and the user identifier under the tag `user_id`.

Recovery data comes from Apple Health via the **Health Auto Export** iOS app, not from the Android app — see Screen 5.

## Screen 1 — Login

| Component | Name | Purpose |
|---|---|---|
| TextBox | EmailTextBox | User email address |
| PasswordTextBox | PasswordTextBox | User password |
| Button | LoginButton | Sends login request |
| Web | LoginWeb | Calls the backend |
| TinyDB | TinyDB1 | Stores token and user ID |

Set `LoginWeb.Url` to `{SERVER_URL}/auth/login`. Set `LoginWeb.RequestHeaders` to a list containing `Content-Type: application/json`. On `LoginButton.Click`, call `LoginWeb.PostText` with this JSON body.

```json
{"email":"user@example.com","password":"password123"}
```

When `LoginWeb.GotText` fires, decode the JSON text into a dictionary. Store `token` in TinyDB tag `token`, `user_id` in TinyDB tag `user_id`, and `webhook_token` in TinyDB tag `webhook_token`. Then open `Screen2`.

## Screen 2 — Dashboard

| Component | Name | Purpose |
|---|---|---|
| Label | RecoveryLabel | Shows readiness zone and color |
| Label | InsightLabel | Shows SHAP recovery insight |
| ListView | ScheduleListView | Shows today's schedule |
| TextBox | NaturalInputTextBox | Natural language task entry |
| Button | SubmitTaskButton | Sends natural language text |
| Button | RateMyDayButton | Opens Screen4 |
| Button | HealthSetupButton | Opens Screen5 |
| Web | RecoveryWeb | Calls `/recovery/today` |
| Web | ScheduleWeb | Calls `/schedule/today` or `/parse-input` |
| TinyDB | TinyDB1 | Reads token and user ID |

On screen initialize, set the Web request headers to include `Authorization: Bearer [TinyDB token]`. Call `RecoveryWeb.Get` with URL `{SERVER_URL}/recovery/today`. The response format is one-level JSON.

```json
{"readiness_zone":"normal","readiness_band":"MEDIUM","predicted_hrv":45,"baseline_hrv":44,"shap_insight":"Features are within normal ranges"}
```

Set `RecoveryLabel.Text` to the readiness zone. Use green for `optimal` or `excellent`, yellow for `normal`, `good`, or `fair`, and red for `fatigued` or `poor`. Set `InsightLabel.Text` to `shap_insight`.

Call `ScheduleWeb.Get` with URL `{SERVER_URL}/schedule/today`. The response is a flat list.

```json
[
  {"id":"...","task":"Morning Prayer","start":"06:00","end":"06:30","location":"Home","type":"routine","is_locked":false}
]
```

Decode the list and build a display list in this format: `HH:MM – HH:MM | Task | Type`. Set that display list as `ScheduleListView.Elements`.

When `SubmitTaskButton.Click` fires, set `ScheduleWeb.Url` to `{SERVER_URL}/parse-input`, keep the authorization header, and call `PostText` with this JSON body.

```json
{"text":"I want to go to the gym and study today","user_id":"[TinyDB user_id]"}
```

The response is the updated flat schedule list. Rebuild `ScheduleListView.Elements` from it.

## Screen 3 — Add and View Goals

| Component | Name | Purpose |
|---|---|---|
| TextBox | GoalNameTextBox | Goal name |
| TextBox | DurationTextBox | Duration in minutes |
| TextBox | LocationTextBox | Location name |
| Spinner | PrioritySpinner | Values 1, 2, 3 |
| Button | AddGoalButton | Creates goal |
| ListView | GoalsListView | Lists today's goals |
| Web | GoalsWeb | Calls `/goals` |
| TinyDB | TinyDB1 | Reads token |

For viewing goals, call `GET {SERVER_URL}/goals?date=YYYY-MM-DD` with `Authorization: Bearer [TinyDB token]`. The response is a flat list.

```json
[{"id":"...","name":"Gym","duration_minutes":90,"location_name":"Gym","lat":null,"lng":null,"priority":3,"date":"2026-05-05"}]
```

For adding a goal, call `POST {SERVER_URL}/goals` with this body.

```json
{"name":"Gym","duration_minutes":90,"location_name":"Gym","priority":3,"date":"2026-05-05"}
```

On long press in `GoalsListView`, store the selected goal ID and call `DELETE {SERVER_URL}/goals/{id}` with the same authorization header. Refresh the list after a successful delete.

## Screen 4 — Rate My Day

| Component | Name | Purpose |
|---|---|---|
| Label | PromptLabel | Displays "How was your day?" |
| Button | Rate1Button … Rate5Button | One per rating value |
| Label | ConfirmationLabel | Shows success message |
| Web | RatingWeb | Calls `/schedule/rate` |
| TinyDB | TinyDB1 | Reads token |

Set `RatingWeb.Url` to `{SERVER_URL}/schedule/rate`. Set request headers to `Content-Type: application/json` and `Authorization: Bearer [TinyDB token]`. When a rating button is tapped, call `PostText` with this body, replacing `N` with the selected number.

```json
{"rating":4}
```

The response is one-level JSON.

```json
{"rating":4}
```

Set `ConfirmationLabel.Text` to `Thanks, your rating was saved.` and close the screen or navigate back to `Screen2`.

## Screen 5 — Health Auto Export Setup (Apple Health bridge)

DaySync's recovery model needs Apple Health data: HRV, daily-average heart rate, sleep duration, and steps. Since App Inventor cannot read Apple Health directly, the user installs the **Health Auto Export** iOS app on their iPhone and configures it to POST data to their personal webhook URL on the DaySync backend.

This screen displays that URL with a copy button so the user can paste it into the iPhone app once.

| Component | Name | Purpose |
|---|---|---|
| Label | InstructionsLabel | Setup steps |
| Label | WebhookUrlLabel | Shows the user's webhook URL |
| Button | CopyUrlButton | Copies the URL to clipboard |
| Button | RotateTokenButton | Generates a new URL if compromised |
| Web | WebhookWeb | Calls `/health/webhook-url` |
| TinyDB | TinyDB1 | Reads token |

On screen initialize, call `GET {SERVER_URL}/health/webhook-url` with `Authorization: Bearer [TinyDB token]`. Response:

```json
{"url":"https://boggle-molar-consensus.ngrok-free.dev/health/webhook/<token>","token":"<token>","method":"POST","content_type":"application/json","note":"..."}
```

Set `WebhookUrlLabel.Text` to the `url` field. The `CopyUrlButton.Click` handler should use the `Clipboard` extension to copy the URL.

Set `InstructionsLabel.Text` to:

> 1. Install **Health Auto Export — JSON+CSV** from the App Store on your iPhone.
> 2. Grant it Apple Health read access for HRV, Heart Rate, Sleep Analysis, and Step Count.
> 3. In the app, open **Automations → New Automation → REST API**.
> 4. Paste this URL into the URL field. Method = POST. Content-Type = application/json. Format = JSON.
> 5. Select metrics: Heart Rate Variability, Heart Rate, Resting Heart Rate, Sleep Analysis, Step Count.
> 6. Schedule = every hour (or as desired). Turn on Background Sync.
> 7. Tap Manual Export once to seed the last 14 days of history.

For `RotateTokenButton.Click`, call `POST {SERVER_URL}/health/webhook-url/rotate` with the same authorization header. Response has a fresh `url` — update the label and prompt the user to update Health Auto Export with the new URL.

## Endpoint Summary

| Purpose | Method | URL | Auth Header | Body |
|---|---|---|---|---|
| Register | POST | `/auth/register` | No | `{"email":"...","password":"..."}` |
| Login | POST | `/auth/login` | No | `{"email":"...","password":"..."}` |
| User profile | GET | `/users/me` | Yes | None |
| Update profile | PATCH | `/users/me` | Yes | Any subset of profile fields |
| Recovery | GET | `/recovery/today` | Yes | None |
| Schedule | GET | `/schedule/today` | Yes | None |
| Rerun scheduler | POST | `/schedule/rerun` | Yes | None |
| Edit item | PATCH | `/schedule/items/{id}` | Yes | `{"start_time":"HH:MM"}` or `{"is_locked":true}` |
| Natural input | POST | `/parse-input` | Yes | `{"text":"...","user_id":"..."}` |
| Rate day | POST | `/schedule/rate` | Yes | `{"rating":N}` |
| Add goal | POST | `/goals` | Yes | Goal JSON |
| List goals | GET | `/goals?date=YYYY-MM-DD` | Yes | None |
| Delete goal | DELETE | `/goals/{id}` | Yes | None |
| Add routine | POST | `/routines` | Yes | Routine JSON |
| List routines | GET | `/routines` | Yes | None |
| Delete routine | DELETE | `/routines/{id}` | Yes | None |
| Get webhook URL | GET | `/health/webhook-url` | Yes | None |
| Rotate webhook | POST | `/health/webhook-url/rotate` | Yes | None |
| Recent samples | GET | `/health/samples/recent?days=14` | Yes | None |
| Health Auto Export | POST | `/health/webhook/{token}` | No (token IS auth) | HAE JSON payload |
| Dev simulate | GET | `/dev/simulate` | Yes | None |
