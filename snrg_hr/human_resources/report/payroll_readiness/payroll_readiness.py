import frappe
from frappe import _
from frappe.utils import getdate

from snrg_hr.services.payroll_control_service import PayrollControlService


def execute(filters=None):
	filters = filters or {}
	start_date = getdate(filters.get("start_date"))
	end_date = getdate(filters.get("end_date"))

	readiness = PayrollControlService().get_readiness(start_date, end_date)

	columns = [
		{"label": _("Check"), "fieldname": "check_name", "fieldtype": "Data", "width": 240},
		{"label": _("Value"), "fieldname": "value", "fieldtype": "Data", "width": 240},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": _("Details"), "fieldname": "details", "fieldtype": "Small Text", "width": 420},
	]

	data = [
		{
			"check_name": _("Attendance Pending From"),
			"value": readiness.get("pending_from_date") or _("Not set"),
			"status": "Warning" if readiness.get("pending_from_date") and getdate(readiness["pending_from_date"]) <= end_date else "OK",
			"details": _("Attendance must be fully covered through the payroll period."),
		},
		{
			"check_name": _("Last Attendance Uploaded Till"),
			"value": readiness.get("last_attendance_uploaded_till_date") or _("Not set"),
			"status": "OK",
			"details": _("Latest processed attendance coverage date."),
		},
		{
			"check_name": _("Unresolved Corrections"),
			"value": readiness.get("unresolved_corrections", 0),
			"status": "Warning" if readiness.get("unresolved_corrections") else "OK",
			"details": _("Draft and submitted correction requests inside the payroll period."),
		},
		{
			"check_name": _("Missing Biometric Codes"),
			"value": readiness.get("missing_biometric_codes", 0),
			"status": "Warning" if readiness.get("missing_biometric_codes") else "OK",
			"details": _("Employees missing biometric mapping can block full attendance coverage."),
		},
		{
			"check_name": _("Locked Attendance Rows"),
			"value": readiness.get("locked_attendance_rows", 0),
			"status": "OK",
			"details": _("Attendance rows already locked in the selected period."),
		},
		{
			"check_name": _("Overall Payroll Readiness"),
			"value": _("Ready") if readiness.get("ready") else _("Not Ready"),
			"status": "OK" if readiness.get("ready") else "Warning",
			"details": "\n".join(readiness.get("issues") or [_("No blocking issues found.")]),
		},
	]

	return columns, data
