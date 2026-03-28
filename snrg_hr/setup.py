import frappe


EMPLOYEE_CUSTOM_FIELDS = [
	{
		"fieldname": "custom_biometric_employee_code",
		"fieldtype": "Data",
		"label": "Biometric Employee Code",
		"insert_after": "attendance_device_id",
		"unique": 1,
	},
	{
		"fieldname": "custom_reporting_manager_employee",
		"fieldtype": "Link",
		"label": "Reporting Manager Employee",
		"options": "Employee",
		"insert_after": "reports_to",
	},
	{
		"fieldname": "custom_weekly_attendance_email_opt_in",
		"fieldtype": "Check",
		"label": "Weekly Attendance Email Opt In",
		"insert_after": "custom_reporting_manager_employee",
		"default": "1",
	},
]

ATTENDANCE_CUSTOM_FIELDS = [
	{"fieldname": "custom_first_in_time", "fieldtype": "Datetime", "label": "First In Time", "insert_after": "shift"},
	{"fieldname": "custom_last_out_time", "fieldtype": "Datetime", "label": "Last Out Time", "insert_after": "custom_first_in_time"},
	{"fieldname": "custom_working_hours", "fieldtype": "Float", "label": "Working Hours", "insert_after": "custom_last_out_time"},
	{"fieldname": "custom_late_minutes", "fieldtype": "Int", "label": "Late Minutes", "insert_after": "custom_working_hours"},
	{"fieldname": "custom_shortfall_minutes", "fieldtype": "Int", "label": "Shortfall Minutes", "insert_after": "custom_late_minutes"},
	{"fieldname": "custom_monthly_late_count", "fieldtype": "Int", "label": "Monthly Late Count", "insert_after": "custom_shortfall_minutes"},
	{"fieldname": "custom_monthly_short_hours_count", "fieldtype": "Int", "label": "Monthly Short Hours Count", "insert_after": "custom_monthly_late_count"},
	{"fieldname": "custom_late_flag", "fieldtype": "Check", "label": "Late Flag", "insert_after": "custom_monthly_short_hours_count"},
	{"fieldname": "custom_short_hours_flag", "fieldtype": "Check", "label": "Short Hours Flag", "insert_after": "custom_late_flag"},
	{"fieldname": "custom_short_hours_grace_used", "fieldtype": "Check", "label": "Short Hours Grace Used", "insert_after": "custom_short_hours_flag"},
	{"fieldname": "custom_missing_punch_warning", "fieldtype": "Check", "label": "Missing Punch Warning", "insert_after": "custom_short_hours_grace_used"},
	{"fieldname": "custom_policy_violation", "fieldtype": "Small Text", "label": "Policy Violation", "insert_after": "custom_missing_punch_warning"},
	{"fieldname": "custom_processed_by_policy_engine", "fieldtype": "Check", "label": "Processed By Policy Engine", "insert_after": "custom_policy_violation"},
	{"fieldname": "custom_import_batch", "fieldtype": "Link", "label": "Import Batch", "options": "Attendance Import Batch", "insert_after": "custom_processed_by_policy_engine"},
	{"fieldname": "custom_attendance_locked", "fieldtype": "Check", "label": "Attendance Locked", "insert_after": "custom_import_batch"},
]

SALARY_SLIP_CUSTOM_FIELDS = [
	{"fieldname": "custom_attendance_finalized", "fieldtype": "Check", "label": "Attendance Finalized", "insert_after": "posting_date"},
	{"fieldname": "custom_half_day_count", "fieldtype": "Float", "label": "Half Day Count", "insert_after": "custom_attendance_finalized"},
	{"fieldname": "custom_late_half_day_count", "fieldtype": "Float", "label": "Late Half Day Count", "insert_after": "custom_half_day_count"},
	{"fieldname": "custom_short_hours_half_day_count", "fieldtype": "Float", "label": "Short Hours Half Day Count", "insert_after": "custom_late_half_day_count"},
	{"fieldname": "custom_attendance_summary_snapshot", "fieldtype": "Long Text", "label": "Attendance Summary Snapshot", "insert_after": "custom_short_hours_half_day_count"},
]

EMPLOYEE_CHECKIN_CUSTOM_FIELDS = [
	{"fieldname": "custom_import_batch", "fieldtype": "Link", "label": "Import Batch", "options": "Attendance Import Batch", "insert_after": "skip_auto_attendance"},
	{"fieldname": "custom_source_file_name", "fieldtype": "Data", "label": "Source File Name", "insert_after": "custom_import_batch"},
	{"fieldname": "custom_source_row_number", "fieldtype": "Int", "label": "Source Row Number", "insert_after": "custom_source_file_name"},
]


def after_install():
	ensure_custom_fields()


def after_migrate():
	ensure_custom_fields()


def ensure_custom_fields():
	ensure_doctype_custom_fields("Employee", EMPLOYEE_CUSTOM_FIELDS)
	ensure_doctype_custom_fields("Attendance", ATTENDANCE_CUSTOM_FIELDS)
	ensure_doctype_custom_fields("Salary Slip", SALARY_SLIP_CUSTOM_FIELDS)
	ensure_doctype_custom_fields("Employee Checkin", EMPLOYEE_CHECKIN_CUSTOM_FIELDS)
	frappe.db.commit()


def ensure_doctype_custom_fields(doctype, field_defs):
	for field_def in field_defs:
		ensure_custom_field(doctype, field_def)


def ensure_custom_field(doctype, field_def):
	fieldname = field_def["fieldname"]
	custom_field_name = f"{doctype}-{fieldname}"
	if frappe.db.exists("Custom Field", custom_field_name):
		for key, value in field_def.items():
			frappe.db.set_value("Custom Field", custom_field_name, key, value, update_modified=False)
		return

	doc = {"doctype": "Custom Field", "dt": doctype}
	doc.update(field_def)
	frappe.get_doc(doc).insert(ignore_permissions=True)
