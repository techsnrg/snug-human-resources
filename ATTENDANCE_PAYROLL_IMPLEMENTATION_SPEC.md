# ERPNext Attendance-to-Payroll Implementation Spec

This document converts the approved attendance-to-payroll plan into a developer-facing implementation blueprint for an ERPNext custom app.

## Status

- Business policy: frozen
- Phase: implementation planning
- Source attendance system: IAS export files
- System of record for policy decisions: ERPNext

## Build Goal

Build a custom ERPNext module that imports weekly raw biometric logs exported from IAS, tracks pending attendance coverage dates, computes attendance outcomes using the approved late-coming and short-hours rules, supports corrections and hierarchy-based visibility, and locks finalized attendance into payroll with full auditability.

## Recommended App Structure

Create a dedicated custom app, for example `snrg_hr_attendance`, and keep all attendance-control logic there instead of scattering it across Client Scripts and Server Scripts.

Suggested areas:

- `doctype/attendance_control_settings`
- `doctype/attendance_import_batch`
- `doctype/attendance_violation_log`
- `doctype/attendance_correction_request`
- `page/attendance_upload_control`
- `api/import_preview.py`
- `api/import_process.py`
- `services/checkin_importer.py`
- `services/attendance_policy_engine.py`
- `services/counter_service.py`
- `services/notification_service.py`
- `services/payroll_lock_service.py`
- `services/correction_service.py`
- `report/manager_team_attendance`
- `report/payroll_readiness`
- `patches/`
- `tests/`

## Standard ERPNext Objects Used

- `Employee`
- `Shift Type`
- `Shift Assignment`
- `Employee Checkin`
- `Attendance`
- `Salary Slip`
- `Payroll Entry`

## Custom Doctypes

### 1. Attendance Control Settings

Purpose:
Central policy configuration and system memory state.

Key fields:

- `last_attendance_uploaded_till_date`
- `next_pending_attendance_from_date`
- `weekly_upload_day`
- `correction_window_end_day_time`
- `payroll_freeze_day`
- `duplicate_punch_threshold_minutes`
- `required_working_hours`
- `short_hours_grace_minutes`
- `allowed_late_count_per_month`
- `allowed_short_hours_grace_count_per_month`
- `late_start_time`
- `late_cutoff_time`
- `pending_upload_alert_days`
- `backdated_import_limit_days`
- `admin_override_role`

Notes:

- Make this a singleton doctype.
- This doctype is the source of truth for pending-date memory.

### 2. Attendance Import Batch

Purpose:
Track every upload attempt and processing outcome.

Key fields:

- `uploaded_by`
- `uploaded_on`
- `source_file`
- `source_file_name`
- `file_date_from`
- `file_date_to`
- `suggested_pending_from_date`
- `suggested_pending_to_date`
- `total_rows`
- `imported_rows`
- `duplicate_rows`
- `rejected_rows`
- `unmatched_employee_rows`
- `invalid_timestamp_rows`
- `locked_period_rows`
- `processing_status`
- `error_summary`
- `last_attendance_covered_till_date`
- `next_pending_attendance_from_date`
- `remarks`

Suggested statuses:

- `Draft`
- `Validated`
- `Partially Processed`
- `Processed`
- `Failed`

### 3. Attendance Violation Log

Purpose:
Capture every policy-triggered warning, conversion, assumption, or override.

Key fields:

- `employee`
- `attendance_date`
- `first_in_time`
- `last_out_time`
- `working_hours`
- `shift_start`
- `late_minutes`
- `shortfall_minutes`
- `violation_type`
- `final_attendance_status`
- `payroll_impact`
- `notes`
- `linked_import_batch`
- `linked_attendance`
- `is_manual_override`

Violation type values:

- `Late Entry`
- `Third Late Converted to Half Day`
- `After 11 AM Half Day`
- `Short Hours Grace Used`
- `Short Hours Grace Exhausted`
- `Below Minimum Hours`
- `Missing Punch Assumed Shift End`
- `Manual Override`

### 4. Attendance Correction Request

Purpose:
Manage correction submission, approval, and reprocessing.

Key fields:

- `employee`
- `attendance_date`
- `current_status`
- `requested_correction`
- `reason`
- `evidence_attachment`
- `submitted_on`
- `correction_deadline`
- `approved_by`
- `approval_status`
- `final_decision`
- `reprocessed_flag`
- `remarks`
- `linked_attendance`
- `linked_import_batch`

## Custom Fields

### Employee

- `custom_biometric_employee_code`
- `custom_reporting_manager_employee`
- `custom_weekly_attendance_email_opt_in`

### Attendance

- `custom_first_in_time`
- `custom_last_out_time`
- `custom_working_hours`
- `custom_late_minutes`
- `custom_shortfall_minutes`
- `custom_monthly_late_count`
- `custom_monthly_short_hours_count`
- `custom_late_flag`
- `custom_short_hours_flag`
- `custom_short_hours_grace_used`
- `custom_missing_punch_warning`
- `custom_policy_violation`
- `custom_processed_by_policy_engine`
- `custom_import_batch`
- `custom_attendance_locked`

### Salary Slip

- `custom_attendance_finalized`
- `custom_half_day_count`
- `custom_late_half_day_count`
- `custom_short_hours_half_day_count`
- `custom_attendance_summary_snapshot`

## Upload Page Requirements

Create a custom page instead of relying on the generic data import tool.

Display:

- Last attendance uploaded till
- Attendance pending from
- Suggested upload date range
- Last successful import batch
- Unresolved corrections count
- Unprocessed batches count

Actions:

- Upload CSV/XLSX
- Preview file
- Validate rows
- Confirm import
- Process attendance
- Send weekly emails

## IAS File Contract

Import raw punch events only.

Required columns:

- `biometric_employee_code`
- `punch_timestamp`
- `punch_date`
- `punch_time`
- `direction` if available
- `device_id`
- `device_location`
- `source_file_name`
- `source_row_number`

Rules:

- One row must represent one punch event.
- Ignore IAS-calculated attendance summaries.

## Processing Pipeline

### Stage 1. Preview

Validate without committing:

- file date range
- total rows
- unmatched biometric IDs
- duplicate rows
- invalid timestamps
- overlap with already uploaded date range
- rows in payroll-locked periods

Preview must require explicit confirmation before import.

### Stage 2. Batch Creation

Create `Attendance Import Batch` before row processing starts.

### Stage 3. Row Validation

Reject rows when:

- employee mapping does not exist
- timestamp is invalid
- date is in the future
- date is in a locked period
- row is a duplicate inside threshold

### Stage 4. Employee Checkin Creation

Create `Employee Checkin` records for valid rows only.

Recommended metadata:

- employee
- time
- log_type if direction can be trusted
- device_id
- device_location
- custom_import_batch
- custom_source_file_name
- custom_source_row_number

### Stage 5. Attendance Recalculation

Reprocess only affected employees and dates from the imported range.

### Stage 6. Control State Update

After successful processing:

- update `last_attendance_uploaded_till_date`
- set `next_pending_attendance_from_date = last_attendance_uploaded_till_date + 1 day`

Important:

- never advance the control date through locked or failed gaps
- pending date must remain visible if a weekly upload is missed

### Stage 7. Notifications

After processing:

- employee weekly summary
- HR/admin control summary
- manager hierarchy summary

## Attendance Policy Engine

This should be implemented as a deterministic service, not inside scattered document events.

### Inputs

- employee
- attendance date
- effective shift assignment
- all valid checkins for that date
- monthly counters up to that date
- holiday/weekly off context

### Derived Values

- first valid in
- last valid out
- working hours
- late minutes
- shortfall minutes
- missing punch warning

### Frozen Policy

Arrival policy:

- `10:00` to `10:30` -> Present
- `10:31` to `11:00` -> Late
- first two late instances in calendar month -> Present with Late flag
- third late onward in calendar month -> Half Day
- after `11:00` -> Half Day

Working-hours policy:

- `>= 9 hours` -> Present
- `>= 8.5 and < 9 hours`:
  - first two instances in calendar month -> Present with short-hours grace
  - third onward -> Half Day
- `< 8.5 hours` -> Half Day

Precedence:

1. Arrival after `11:00` -> Half Day
2. Third late in month -> Half Day
3. Short-hours violation beyond grace -> Half Day
4. Otherwise Present

### Missing Punch Rule

Use Option A:

- if missing OUT punch, assume shift end time provisionally
- set `custom_missing_punch_warning = 1`
- create violation log entry
- include in weekly summary

### Monthly Counters

Maintain per employee, per calendar month:

- `late_count`
- `short_hours_grace_count`

Recommended implementation:

- derive counts from processed `Attendance` records instead of storing a separate mutable counter table unless performance proves it necessary
- always recalculate in date order within an affected month when reprocessing

## Correction Workflow

Workflow:

1. Employee receives weekly summary
2. Employee submits correction before deadline
3. Reporting manager and/or HR reviews
4. Approved record triggers reprocessing of the affected date
5. Final outcome is logged

Rules:

- corrections blocked after configured cutoff unless override role is used
- all manual overrides must capture old value, new value, actor, timestamp, and reason

## Manager Visibility

Managers must see:

- direct reportees
- indirect reportees across the full reporting tree

Recommended approach:

- resolve hierarchy from `custom_reporting_manager_employee`
- create a utility function that returns all subordinate employee IDs recursively
- reuse this function in reports, dashboards, and email summaries

## Payroll Lock and Finalization

Rules:

- payroll must consume finalized `Attendance` only
- after payroll is processed/submitted, attendance becomes locked for that period
- ordinary imports and edits in locked period must be blocked
- override requires admin role and audit trail

Recommended touchpoints:

- hook validation into payroll finalization flow
- mark attendance rows in payroll period with `custom_attendance_locked = 1`
- store salary-slip summary snapshot for audit consistency

## Notifications

### Employee Weekly Summary

Include:

- date
- first in
- last out
- working hours
- final status
- late flag
- short-hours flag
- grace used
- missing punch warning
- month-to-date late count
- month-to-date short-hours grace count
- correction deadline

### HR/Admin Summary

Include:

- latest import status
- pending-from date
- last uploaded till date
- unresolved corrections
- unmatched codes
- duplicate rows
- exhausted late grace
- exhausted short-hours grace
- missing punch cases
- half-day conversions

### Manager Summary

Include team-only visibility:

- employee name
- date
- first in
- last out
- working hours
- final status
- late count this month
- short-hours grace count this month
- missing punch warning

## Recommended Implementation Order

### Phase 1. Foundations

- create custom app
- create doctypes
- add custom fields
- create role permissions
- create singleton settings

### Phase 2. Import Control

- build upload page
- implement file parser
- build preview response
- create import batch persistence
- add duplicate and locked-period validation

### Phase 3. Checkin and Attendance Engine

- create checkins from valid rows
- implement date-range attendance reprocessing
- write violation logs
- update attendance custom fields

### Phase 4. Corrections and Notifications

- correction request workflow
- weekly employee mailer
- HR/admin summary
- manager hierarchy summary

### Phase 5. Payroll Controls and Reports

- payroll readiness validation
- attendance lock logic
- override audit logging
- dashboards and reports

## Testing Matrix

Minimum automated test cases:

- on-time arrival with 9+ hours -> Present
- first late in month with 9+ hours -> Present with late flag
- third late in month -> Half Day
- after 11:00 arrival with 9+ hours -> Half Day
- first short-hours grace case at 8h 50m -> Present with grace
- third short-hours grace case -> Half Day
- below 8.5 hours -> Half Day
- missing OUT punch -> assumed shift end + warning
- duplicate punch within threshold ignored
- locked payroll period import blocked
- pending date remains visible after missed weekly upload
- approved correction reprocesses affected date
- manager report includes indirect subordinates

## Open Technical Assumptions

These assumptions should be confirmed before coding:

- IAS export format is available as CSV or XLSX with stable headers
- employee shift assignments are maintained correctly in ERPNext
- attendance status values remain compatible with ERPNext payroll expectations
- `custom_reporting_manager_employee` will be preferred over any inconsistent standard hierarchy fields
- weekly summary emails are acceptable through ERPNext mail queue

## Immediate Next Step

If development starts in a real ERPNext app workspace, begin with:

1. scaffolding the custom app
2. creating the four doctypes and required custom fields
3. building the upload preview API before the final importer

This order reduces downstream rework and gives the team a working control layer early.
