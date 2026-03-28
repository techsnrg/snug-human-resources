from collections import defaultdict

import frappe
from frappe import _

from snrg_hr.services.attendance_import_preview import AttendanceImportPreviewService
from snrg_hr.services.attendance_policy_engine import AttendancePolicyEngine


class AttendanceBatchProcessor:
	def __init__(self):
		self.preview_service = AttendanceImportPreviewService()
		self.policy_engine = AttendancePolicyEngine()

	def process_batch(self, batch_name: str):
		batch = frappe.get_doc("Attendance Import Batch", batch_name)
		if not batch.source_file:
			frappe.throw(_("The selected batch does not have a source file attached."))

		preview = self.preview_service.preview_file(batch.source_file)
		if preview.get("fatal_errors"):
			batch.db_set("processing_status", "Failed")
			frappe.throw(_("Preview errors must be resolved before processing this batch."))

		file_doc = self.preview_service.get_file_doc(batch.source_file)
		rows, _source_file_name = self.preview_service.read_rows(file_doc)
		header_map = self.preview_service.map_headers(rows[0].keys()) if rows else {}
		normalized_rows = [
			self.preview_service.normalize_row(raw_row, header_map, idx)
			for idx, raw_row in enumerate(rows, start=2)
		]

		employee_map = self._get_employee_map(
			{row["biometric_employee_code"] for row in normalized_rows if row["biometric_employee_code"]}
		)
		locked_dates = self.preview_service.get_locked_attendance_dates()
		created_checkins = 0
		skipped_rows = 0
		affected = defaultdict(set)

		batch.db_set("processing_status", "Partially Processed")

		for row in normalized_rows:
			if row["error"]:
				skipped_rows += 1
				continue

			employee = employee_map.get(row["biometric_employee_code"])
			if not employee:
				skipped_rows += 1
				continue

			attendance_date = row["punch_datetime"].date()
			if attendance_date in locked_dates:
				skipped_rows += 1
				continue

			if self._checkin_exists(employee, row["punch_datetime"]):
				continue

			doc = frappe.new_doc("Employee Checkin")
			doc.employee = employee
			doc.time = row["punch_datetime"]

			log_type = self._normalize_log_type(row.get("direction"))
			if log_type and self._has_field("Employee Checkin", "log_type"):
				doc.log_type = log_type

			if self._has_field("Employee Checkin", "device_id") and row.get("device_id"):
				doc.device_id = row["device_id"]

			if self._has_field("Employee Checkin", "skip_auto_attendance"):
				doc.skip_auto_attendance = 1

			if self._has_field("Employee Checkin", "custom_import_batch"):
				doc.custom_import_batch = batch.name
			if self._has_field("Employee Checkin", "custom_source_file_name"):
				doc.custom_source_file_name = batch.source_file_name
			if self._has_field("Employee Checkin", "custom_source_row_number"):
				doc.custom_source_row_number = row["row_number"]

			doc.insert(ignore_permissions=True)
			created_checkins += 1
			affected[employee].add(attendance_date)

		attendance_results = self.policy_engine.process_affected_dates(
			affected_dates=affected,
			batch_name=batch.name,
		)

		file_dates = [date for dates in affected.values() for date in dates]
		last_covered_till = max(file_dates) if file_dates else batch.file_date_to or batch.file_date_from

		batch.processing_status = "Processed"
		batch.imported_rows = created_checkins
		batch.rejected_rows = skipped_rows
		batch.last_attendance_covered_till_date = last_covered_till
		batch.next_pending_attendance_from_date = self._next_date(last_covered_till)
		batch.remarks = _(
			"Employee Checkins created and attendance recalculated for affected dates."
		)
		batch.save(ignore_permissions=True)

		self._update_control_settings(last_covered_till)

		return {
			"batch_name": batch.name,
			"processing_status": "Processed",
			"created_checkins": created_checkins,
			"skipped_rows": skipped_rows,
			"attendance_results": attendance_results,
			"last_attendance_uploaded_till_date": last_covered_till,
		}

	def _get_employee_map(self, employee_codes):
		if not employee_codes or not self.preview_service.employee_code_field_available():
			return {}

		rows = frappe.get_all(
			"Employee",
			filters={"custom_biometric_employee_code": ["in", list(employee_codes)]},
			fields=["name", "custom_biometric_employee_code"],
		)
		return {row.custom_biometric_employee_code: row.name for row in rows}

	def _checkin_exists(self, employee, checkin_time):
		return frappe.db.exists(
			"Employee Checkin",
			{"employee": employee, "time": checkin_time},
		)

	def _normalize_log_type(self, direction):
		if not direction:
			return None

		value = direction.strip().upper()
		if value in {"IN", "I", "CHECKIN", "PUNCH IN"}:
			return "IN"
		if value in {"OUT", "O", "CHECKOUT", "PUNCH OUT"}:
			return "OUT"
		return None

	def _update_control_settings(self, last_covered_till):
		if not last_covered_till or not frappe.db.exists("DocType", "Attendance Control Settings"):
			return

		settings = frappe.get_single("Attendance Control Settings")
		settings.last_attendance_uploaded_till_date = last_covered_till
		settings.next_pending_attendance_from_date = self._next_date(last_covered_till)
		settings.save(ignore_permissions=True)

	def _next_date(self, date_value):
		if not date_value:
			return None
		from frappe.utils import add_days

		return add_days(date_value, 1)

	def _has_field(self, doctype, fieldname):
		try:
			return frappe.db.has_column(doctype, fieldname)
		except Exception:
			return False
