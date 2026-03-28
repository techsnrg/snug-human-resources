import frappe
from frappe import _
from frappe.utils import getdate

from snrg_hr.services.team_hierarchy import TeamHierarchyService


def execute(filters=None):
	filters = filters or {}
	start_date = getdate(filters.get("start_date"))
	end_date = getdate(filters.get("end_date"))
	current_manager = _get_manager_for_current_user()
	manager_employee = filters.get("manager_employee") or current_manager
	_enforce_manager_scope(manager_employee, current_manager)

	columns = [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 180},
		{"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 180},
		{"label": _("Attendance Date"), "fieldname": "attendance_date", "fieldtype": "Date", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
		{"label": _("First In"), "fieldname": "first_in_time", "fieldtype": "Datetime", "width": 170},
		{"label": _("Last Out"), "fieldname": "last_out_time", "fieldtype": "Datetime", "width": 170},
		{"label": _("Working Hours"), "fieldname": "working_hours", "fieldtype": "Float", "width": 110},
		{"label": _("Late Count"), "fieldname": "monthly_late_count", "fieldtype": "Int", "width": 100},
		{"label": _("Short Hours Count"), "fieldname": "monthly_short_hours_count", "fieldtype": "Int", "width": 130},
		{"label": _("Missing Punch"), "fieldname": "missing_punch_warning", "fieldtype": "Check", "width": 100},
	]

	if not manager_employee:
		return columns, []

	subordinates = TeamHierarchyService().get_all_subordinates(manager_employee)
	if not subordinates:
		return columns, []

	attendance_rows = frappe.get_all(
		"Attendance",
		filters={
			"employee": ["in", subordinates],
			"attendance_date": ["between", [start_date, end_date]],
		},
		fields=[
			"employee",
			"employee_name",
			"attendance_date",
			"status",
			"custom_first_in_time as first_in_time",
			"custom_last_out_time as last_out_time",
			"custom_working_hours as working_hours",
			"custom_monthly_late_count as monthly_late_count",
			"custom_monthly_short_hours_count as monthly_short_hours_count",
			"custom_missing_punch_warning as missing_punch_warning",
		],
		order_by="attendance_date desc, employee asc",
		limit_page_length=0,
	)

	return columns, attendance_rows


def _get_manager_for_current_user():
	user = frappe.session.user
	if user == "Administrator":
		return None

	filters = {}
	if frappe.db.has_column("Employee", "user_id"):
		filters["user_id"] = user
	elif frappe.db.has_column("Employee", "company_email"):
		filters["company_email"] = user
	else:
		return None

	return frappe.db.get_value("Employee", filters, "name")


def _enforce_manager_scope(manager_employee, current_manager):
	if not manager_employee:
		return

	roles = set(frappe.get_roles())
	if {"System Manager", "HR Manager", "HR User"} & roles:
		return

	if not current_manager or manager_employee != current_manager:
		frappe.throw(_("You can only view attendance for your own reporting hierarchy."))
