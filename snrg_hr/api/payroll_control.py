import frappe
from frappe import _

from snrg_hr.services.payroll_control_service import PayrollControlService


@frappe.whitelist()
def get_payroll_readiness(start_date: str, end_date: str):
	if not start_date or not end_date:
		frappe.throw(_("Start date and end date are required."))
	return PayrollControlService().get_readiness(start_date, end_date)


@frappe.whitelist()
def finalize_attendance(start_date: str, end_date: str):
	if not start_date or not end_date:
		frappe.throw(_("Start date and end date are required."))
	return PayrollControlService().finalize_attendance(start_date, end_date)


@frappe.whitelist()
def unlock_attendance_override(attendance_name: str, reason: str):
	if not attendance_name or not reason:
		frappe.throw(_("Attendance record and override reason are required."))
	return PayrollControlService().unlock_attendance_override(attendance_name, reason)


@frappe.whitelist()
def sync_salary_slip_summary(salary_slip_name: str):
	if not salary_slip_name:
		frappe.throw(_("Salary slip is required."))
	return PayrollControlService().sync_salary_slip_summary(salary_slip_name)
