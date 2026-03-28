from datetime import date

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime


class PayrollControlService:
	def get_readiness(self, start_date, end_date):
		start_date = getdate(start_date)
		end_date = getdate(end_date)

		pending_from_date = self._get_setting_value("next_pending_attendance_from_date")
		last_uploaded_till_date = self._get_setting_value("last_attendance_uploaded_till_date")

		issues = []
		if pending_from_date and getdate(pending_from_date) <= end_date:
			issues.append(
				_(
					"Attendance is still pending from {0}. Upload and process missing attendance before payroll."
				).format(pending_from_date)
			)

		unresolved_corrections = frappe.db.count(
			"Attendance Correction Request",
			{
				"attendance_date": ["between", [start_date, end_date]],
				"approval_status": ["in", ["Draft", "Submitted"]],
			},
		)
		if unresolved_corrections:
			issues.append(
				_("{0} correction request(s) are still unresolved in the payroll period.").format(
					unresolved_corrections
				)
			)

		missing_biometric_codes = self._count_missing_biometric_codes()
		if missing_biometric_codes:
			issues.append(
				_("{0} employee(s) are missing biometric employee codes.").format(
					missing_biometric_codes
				)
			)

		unlocked_attendance = self._count_attendance_rows(start_date, end_date, locked=0)
		locked_attendance = self._count_attendance_rows(start_date, end_date, locked=1)

		return {
			"start_date": str(start_date),
			"end_date": str(end_date),
			"last_attendance_uploaded_till_date": last_uploaded_till_date,
			"pending_from_date": pending_from_date,
			"unresolved_corrections": unresolved_corrections,
			"missing_biometric_codes": missing_biometric_codes,
			"attendance_rows": unlocked_attendance + locked_attendance,
			"locked_attendance_rows": locked_attendance,
			"ready": not issues,
			"issues": issues,
		}

	def finalize_attendance(self, start_date, end_date):
		readiness = self.get_readiness(start_date, end_date)
		if not readiness["ready"]:
			frappe.throw(_("Payroll period is not ready for attendance finalization."))

		start_date = getdate(start_date)
		end_date = getdate(end_date)
		attendance_rows = frappe.get_all(
			"Attendance",
			filters={"attendance_date": ["between", [start_date, end_date]]},
			fields=["name", "status"],
		)

		half_day_count = 0
		for row in attendance_rows:
			doc = frappe.get_doc("Attendance", row.name)
			if self._has_field("Attendance", "custom_attendance_locked"):
				doc.custom_attendance_locked = 1
			doc.save(ignore_permissions=True)
			if row.status == "Half Day":
				half_day_count += 1

		return {
			"start_date": str(start_date),
			"end_date": str(end_date),
			"locked_attendance_rows": len(attendance_rows),
			"half_day_count": half_day_count,
			"message": _("Attendance has been finalized and locked for the payroll period."),
		}

	def unlock_attendance_override(self, attendance_name, reason):
		if not attendance_name:
			frappe.throw(_("Attendance record is required for override."))
		if not reason:
			frappe.throw(_("Override reason is required."))

		attendance = frappe.get_doc("Attendance", attendance_name)
		if self._has_field("Attendance", "custom_attendance_locked"):
			attendance.custom_attendance_locked = 0
		attendance.save(ignore_permissions=True)

		self._create_manual_override_violation(attendance, reason)
		return {
			"attendance": attendance.name,
			"message": _("Attendance was unlocked through admin override."),
		}

	def sync_salary_slip_summary(self, salary_slip_name):
		slip = frappe.get_doc("Salary Slip", salary_slip_name)
		start_date = getdate(slip.start_date)
		end_date = getdate(slip.end_date)

		attendance_rows = frappe.get_all(
			"Attendance",
			filters={
				"employee": slip.employee,
				"attendance_date": ["between", [start_date, end_date]],
			},
			fields=["status", "custom_policy_violation"],
		)

		half_day_count = 0
		late_half_day_count = 0
		short_hours_half_day_count = 0
		for row in attendance_rows:
			if row.status == "Half Day":
				half_day_count += 1
				policy_violation = row.custom_policy_violation or ""
				if "Late" in policy_violation or "11 AM" in policy_violation:
					late_half_day_count += 1
				if "Short Hours" in policy_violation or "Below Minimum Hours" in policy_violation:
					short_hours_half_day_count += 1

		if self._has_field("Salary Slip", "custom_attendance_finalized"):
			slip.custom_attendance_finalized = 1
		if self._has_field("Salary Slip", "custom_half_day_count"):
			slip.custom_half_day_count = half_day_count
		if self._has_field("Salary Slip", "custom_late_half_day_count"):
			slip.custom_late_half_day_count = late_half_day_count
		if self._has_field("Salary Slip", "custom_short_hours_half_day_count"):
			slip.custom_short_hours_half_day_count = short_hours_half_day_count
		if self._has_field("Salary Slip", "custom_attendance_summary_snapshot"):
			slip.custom_attendance_summary_snapshot = frappe.as_json(
				{
					"generated_on": str(now_datetime()),
					"period": [str(start_date), str(end_date)],
					"half_day_count": half_day_count,
					"late_half_day_count": late_half_day_count,
					"short_hours_half_day_count": short_hours_half_day_count,
				}
			)
		slip.save(ignore_permissions=True)

		return {
			"salary_slip": slip.name,
			"half_day_count": half_day_count,
			"late_half_day_count": late_half_day_count,
			"short_hours_half_day_count": short_hours_half_day_count,
		}

	def _count_attendance_rows(self, start_date, end_date, locked):
		if locked and not self._has_field("Attendance", "custom_attendance_locked"):
			return 0

		filters = {"attendance_date": ["between", [start_date, end_date]]}
		if self._has_field("Attendance", "custom_attendance_locked"):
			filters["custom_attendance_locked"] = locked

		return frappe.db.count("Attendance", filters)

	def _count_missing_biometric_codes(self):
		if not self._has_field("Employee", "custom_biometric_employee_code"):
			return 0
		return frappe.db.count("Employee", {"custom_biometric_employee_code": ["in", ["", None]]})

	def _get_setting_value(self, fieldname):
		if not frappe.db.exists("DocType", "Attendance Control Settings"):
			return None
		try:
			return frappe.db.get_single_value("Attendance Control Settings", fieldname)
		except Exception:
			return None

	def _create_manual_override_violation(self, attendance, reason):
		if not frappe.db.exists("DocType", "Attendance Violation Log"):
			return

		doc = frappe.new_doc("Attendance Violation Log")
		doc.employee = attendance.employee
		doc.attendance_date = attendance.attendance_date
		doc.linked_attendance = attendance.name
		doc.violation_type = "Manual Override"
		doc.final_attendance_status = attendance.status
		doc.payroll_impact = _("Manual override applied by {0}.").format(frappe.session.user)
		doc.is_manual_override = 1
		doc.notes = reason
		if hasattr(attendance, "custom_first_in_time"):
			doc.first_in_time = attendance.custom_first_in_time
		if hasattr(attendance, "custom_last_out_time"):
			doc.last_out_time = attendance.custom_last_out_time
		if hasattr(attendance, "custom_working_hours"):
			doc.working_hours = attendance.custom_working_hours
		if hasattr(attendance, "custom_late_minutes"):
			doc.late_minutes = attendance.custom_late_minutes
		if hasattr(attendance, "custom_shortfall_minutes"):
			doc.shortfall_minutes = attendance.custom_shortfall_minutes
		doc.insert(ignore_permissions=True)

	def _has_field(self, doctype, fieldname):
		try:
			return frappe.db.has_column(doctype, fieldname)
		except Exception:
			return False
