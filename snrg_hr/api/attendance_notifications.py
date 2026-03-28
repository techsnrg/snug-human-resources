import frappe
from frappe import _

from snrg_hr.services.attendance_notification_service import AttendanceNotificationService


@frappe.whitelist()
def preview_weekly_summary(start_date: str, end_date: str):
	if not start_date or not end_date:
		frappe.throw(_("Start date and end date are required."))
	return AttendanceNotificationService().preview_weekly_summary(start_date, end_date)


@frappe.whitelist()
def send_weekly_summary(start_date: str, end_date: str):
	if not start_date or not end_date:
		frappe.throw(_("Start date and end date are required."))
	return AttendanceNotificationService().send_weekly_summary(start_date, end_date)
