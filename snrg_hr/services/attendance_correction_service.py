from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime

from snrg_hr.services.attendance_policy_engine import AttendancePolicyEngine


class AttendanceCorrectionService:
	def expire_open_requests(self):
		requests = frappe.get_all(
			"Attendance Correction Request",
			filters={"approval_status": ["in", ["Draft", "Submitted"]]},
			fields=["name"],
			limit_page_length=0,
		)
		for row in requests:
			doc = frappe.get_doc("Attendance Correction Request", row.name)
			previous_status = doc.approval_status
			self.expire_if_past_deadline(doc)
			if doc.approval_status != previous_status:
				doc.save(ignore_permissions=True)

	def submit_request(self, request_name: str):
		doc = frappe.get_doc("Attendance Correction Request", request_name)
		if doc.approval_status not in {"Draft", "Rejected"}:
			frappe.throw(_("Only draft or rejected requests can be submitted."))

		if doc.correction_deadline and get_datetime(now_datetime()) > get_datetime(doc.correction_deadline):
			doc.approval_status = "Expired"
			doc.save(ignore_permissions=True)
			frappe.throw(_("The correction deadline has passed for this request."))

		doc.approval_status = "Submitted"
		doc.submitted_on = now_datetime()
		doc.save(ignore_permissions=True)
		return self._response(doc, _("Correction request submitted."))

	def approve_request(self, request_name: str, decision_note: str | None = None):
		doc = frappe.get_doc("Attendance Correction Request", request_name)
		if doc.approval_status not in {"Submitted", "Draft"}:
			frappe.throw(_("Only submitted or draft requests can be approved."))

		doc.approval_status = "Approved"
		doc.approved_by = frappe.session.user
		if decision_note:
			doc.final_decision = decision_note
		doc.save(ignore_permissions=True)

		reprocess_result = self.reprocess_request(request_name)
		return self._response(doc, _("Correction request approved and attendance reprocessed."), reprocess_result)

	def reject_request(self, request_name: str, decision_note: str | None = None):
		doc = frappe.get_doc("Attendance Correction Request", request_name)
		if doc.approval_status not in {"Submitted", "Draft"}:
			frappe.throw(_("Only submitted or draft requests can be rejected."))

		doc.approval_status = "Rejected"
		doc.approved_by = frappe.session.user
		if decision_note:
			doc.final_decision = decision_note
		doc.save(ignore_permissions=True)
		return self._response(doc, _("Correction request rejected."))

	def reprocess_request(self, request_name: str):
		doc = frappe.get_doc("Attendance Correction Request", request_name)
		if doc.approval_status != "Approved":
			frappe.throw(_("Only approved correction requests can be reprocessed."))

		engine = AttendancePolicyEngine()
		result = engine.process_affected_dates(
			affected_dates={doc.employee: {getdate(doc.attendance_date)}},
			batch_name=doc.linked_import_batch,
		)
		doc.reprocessed_flag = 1
		doc.save(ignore_permissions=True)
		return result

	def populate_request_context(self, doc):
		attendance = self._get_attendance(doc.employee, doc.attendance_date)
		if attendance:
			doc.linked_attendance = attendance.name
			doc.current_status = attendance.status
			if hasattr(attendance, "custom_import_batch"):
				doc.linked_import_batch = attendance.custom_import_batch

		if not doc.correction_deadline:
			doc.correction_deadline = self.get_correction_deadline(doc.attendance_date)
		if not doc.submitted_on:
			doc.submitted_on = now_datetime()

	def get_correction_deadline(self, attendance_date):
		settings_text = self._get_deadline_setting()
		base_date = getdate(attendance_date)
		target_day, target_hour, target_minute = self._parse_deadline_setting(settings_text)

		current = datetime.combine(base_date, datetime.min.time())
		for _ in range(8):
			if current.strftime("%A").lower() == target_day:
				return current.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
			current = current + timedelta(days=1)

		return current.replace(hour=13, minute=0, second=0, microsecond=0)

	def expire_if_past_deadline(self, doc):
		if doc.approval_status in {"Approved", "Rejected", "Expired"}:
			return
		if doc.correction_deadline and get_datetime(now_datetime()) > get_datetime(doc.correction_deadline):
			doc.approval_status = "Expired"

	def _get_attendance(self, employee, attendance_date):
		if not employee or not attendance_date or not frappe.db.exists("DocType", "Attendance"):
			return None

		name = frappe.db.exists(
			"Attendance",
			{"employee": employee, "attendance_date": attendance_date},
		)
		return frappe.get_doc("Attendance", name) if name else None

	def _get_deadline_setting(self):
		if not frappe.db.exists("DocType", "Attendance Control Settings"):
			return "Monday 13:00"
		try:
			settings = frappe.get_single("Attendance Control Settings")
			return settings.get("correction_window_end_day_time") or "Monday 13:00"
		except Exception:
			return "Monday 13:00"

	def _parse_deadline_setting(self, text):
		if not text:
			return "monday", 13, 0
		parts = text.split()
		day = parts[0].strip().lower() if parts else "monday"
		time_part = parts[1].strip() if len(parts) > 1 else "13:00"
		try:
			hour_str, minute_str = time_part.split(":", 1)
			return day, int(hour_str), int(minute_str)
		except Exception:
			return day, 13, 0

	def _response(self, doc, message, reprocess_result=None):
		return {
			"name": doc.name,
			"approval_status": doc.approval_status,
			"reprocessed_flag": doc.reprocessed_flag,
			"message": message,
			"reprocess_result": reprocess_result or [],
		}
