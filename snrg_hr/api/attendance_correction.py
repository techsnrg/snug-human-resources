import frappe
from frappe import _

from snrg_hr.services.attendance_correction_service import AttendanceCorrectionService


@frappe.whitelist()
def submit_request(request_name: str):
	if not request_name:
		frappe.throw(_("Attendance correction request is required."))
	return AttendanceCorrectionService().submit_request(request_name)


@frappe.whitelist()
def approve_request(request_name: str, decision_note: str | None = None):
	if not request_name:
		frappe.throw(_("Attendance correction request is required."))
	return AttendanceCorrectionService().approve_request(request_name, decision_note)


@frappe.whitelist()
def reject_request(request_name: str, decision_note: str | None = None):
	if not request_name:
		frappe.throw(_("Attendance correction request is required."))
	return AttendanceCorrectionService().reject_request(request_name, decision_note)


@frappe.whitelist()
def reprocess_request(request_name: str):
	if not request_name:
		frappe.throw(_("Attendance correction request is required."))
	return AttendanceCorrectionService().reprocess_request(request_name)
