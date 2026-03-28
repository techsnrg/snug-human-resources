from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from snrg_hr.services.team_hierarchy import TeamHierarchyService


class AttendanceNotificationService:
	def __init__(self):
		self.hierarchy = TeamHierarchyService()

	def should_send_weekly_summary_today(self):
		configured_day = self._get_single_value("Attendance Control Settings", "weekly_upload_day")
		configured_day = (configured_day or "Saturday").strip().lower()
		today_name = getdate(nowdate()).strftime("%A").lower()
		return configured_day == today_name

	def preview_weekly_summary(self, start_date, end_date):
		start_date = getdate(start_date)
		end_date = getdate(end_date)

		attendance_rows = frappe.get_all(
			"Attendance",
			filters={"attendance_date": ["between", [start_date, end_date]]},
			fields=[
				"name",
				"employee",
				"attendance_date",
				"status",
				"custom_first_in_time",
				"custom_last_out_time",
				"custom_working_hours",
				"custom_late_flag",
				"custom_short_hours_flag",
				"custom_short_hours_grace_used",
				"custom_missing_punch_warning",
				"custom_monthly_late_count",
				"custom_monthly_short_hours_count",
			],
			order_by="employee asc, attendance_date asc",
			limit_page_length=0,
		)

		employee_map = self._get_employee_map({row.employee for row in attendance_rows})
		employee_payload = defaultdict(list)
		for row in attendance_rows:
			employee_payload[row.employee].append(row)

		employee_summaries = []
		for employee, rows in employee_payload.items():
			employee_doc = employee_map.get(employee, {})
			employee_summaries.append(
				{
					"employee": employee,
					"employee_name": employee_doc.get("employee_name") or employee,
					"recipient_email": employee_doc.get("prefered_email") or employee_doc.get("company_email"),
					"days": [self._serialize_attendance_row(row) for row in rows],
					"totals": self._summarize_rows(rows),
				}
			)

		hr_summary = self._build_hr_summary(start_date, end_date, attendance_rows)
		manager_summaries = self._build_manager_summaries(start_date, end_date, attendance_rows, employee_map)

		return {
			"start_date": str(start_date),
			"end_date": str(end_date),
			"employee_summaries": employee_summaries,
			"hr_summary": hr_summary,
			"manager_summaries": manager_summaries,
		}

	def send_weekly_summary(self, start_date, end_date):
		payload = self.preview_weekly_summary(start_date, end_date)

		sent_employee_emails = 0
		for summary in payload["employee_summaries"]:
			if not summary["recipient_email"]:
				continue
			frappe.sendmail(
				recipients=[summary["recipient_email"]],
				subject=_("Weekly Attendance Summary: {0} to {1}").format(
					payload["start_date"], payload["end_date"]
				),
				message=self._employee_message(summary, payload["start_date"], payload["end_date"]),
			)
			sent_employee_emails += 1

		hr_recipients = self._get_role_emails("HR Manager")
		if hr_recipients:
			frappe.sendmail(
				recipients=hr_recipients,
				subject=_("Weekly Attendance Control Summary: {0} to {1}").format(
					payload["start_date"], payload["end_date"]
				),
				message=self._hr_message(payload["hr_summary"]),
			)

		manager_emails_sent = 0
		for summary in payload["manager_summaries"]:
			if not summary.get("recipient_email"):
				continue
			frappe.sendmail(
				recipients=[summary["recipient_email"]],
				subject=_("Team Attendance Summary: {0} to {1}").format(
					payload["start_date"], payload["end_date"]
				),
				message=self._manager_message(summary, payload["start_date"], payload["end_date"]),
			)
			manager_emails_sent += 1

		return {
			"start_date": payload["start_date"],
			"end_date": payload["end_date"],
			"employee_emails_sent": sent_employee_emails,
			"manager_emails_sent": manager_emails_sent,
			"hr_emails_sent": len(hr_recipients),
		}

	def _build_hr_summary(self, start_date, end_date, attendance_rows):
		pending_from_date = self._get_single_value("Attendance Control Settings", "next_pending_attendance_from_date")
		last_uploaded_till_date = self._get_single_value(
			"Attendance Control Settings", "last_attendance_uploaded_till_date"
		)
		latest_batch = frappe.get_all(
			"Attendance Import Batch",
			fields=["name", "processing_status", "source_file_name"],
			order_by="modified desc",
			limit=1,
		)
		unresolved_corrections = frappe.db.count(
			"Attendance Correction Request",
			{
				"attendance_date": ["between", [start_date, end_date]],
				"approval_status": ["in", ["Draft", "Submitted"]],
			},
		)
		missing_punch_cases = sum(1 for row in attendance_rows if getattr(row, "custom_missing_punch_warning", 0))
		half_day_conversions = sum(1 for row in attendance_rows if row.status == "Half Day")
		exhausted_late_grace = sum(
			1 for row in attendance_rows if getattr(row, "custom_monthly_late_count", 0) and row.status == "Half Day"
		)
		exhausted_short_hours = sum(
			1
			for row in attendance_rows
			if getattr(row, "custom_monthly_short_hours_count", 0) and row.status == "Half Day"
		)

		return {
			"pending_from_date": pending_from_date,
			"last_uploaded_till_date": last_uploaded_till_date,
			"latest_batch": latest_batch[0] if latest_batch else None,
			"unresolved_corrections": unresolved_corrections,
			"missing_punch_cases": missing_punch_cases,
			"half_day_conversions": half_day_conversions,
			"exhausted_late_grace": exhausted_late_grace,
			"exhausted_short_hours": exhausted_short_hours,
		}

	def _build_manager_summaries(self, start_date, end_date, attendance_rows, employee_map):
		rows_by_employee = defaultdict(list)
		for row in attendance_rows:
			rows_by_employee[row.employee].append(row)

		manager_payload = []
		for employee, employee_doc in employee_map.items():
			subordinates = self.hierarchy.get_all_subordinates(employee)
			if not subordinates:
				continue
			team_rows = []
			for subordinate in subordinates:
				for row in rows_by_employee.get(subordinate, []):
					team_rows.append(self._serialize_attendance_row(row))

			if not team_rows:
				continue

			manager_payload.append(
				{
					"manager_employee": employee,
					"manager_name": employee_doc.get("employee_name") or employee,
					"recipient_email": employee_doc.get("prefered_email") or employee_doc.get("company_email"),
					"team_size": len(subordinates),
					"rows": team_rows,
				}
			)

		return manager_payload

	def _serialize_attendance_row(self, row):
		return {
			"employee": row.employee,
			"attendance_date": str(row.attendance_date),
			"status": row.status,
			"first_in_time": str(getattr(row, "custom_first_in_time", "") or ""),
			"last_out_time": str(getattr(row, "custom_last_out_time", "") or ""),
			"working_hours": getattr(row, "custom_working_hours", 0),
			"late_flag": getattr(row, "custom_late_flag", 0),
			"short_hours_flag": getattr(row, "custom_short_hours_flag", 0),
			"short_hours_grace_used": getattr(row, "custom_short_hours_grace_used", 0),
			"missing_punch_warning": getattr(row, "custom_missing_punch_warning", 0),
			"monthly_late_count": getattr(row, "custom_monthly_late_count", 0),
			"monthly_short_hours_count": getattr(row, "custom_monthly_short_hours_count", 0),
		}

	def _summarize_rows(self, rows):
		present_days = sum(1 for row in rows if row.status == "Present")
		half_days = sum(1 for row in rows if row.status == "Half Day")
		missing_punch_days = sum(1 for row in rows if getattr(row, "custom_missing_punch_warning", 0))
		latest_row = rows[-1] if rows else None
		return {
			"present_days": present_days,
			"half_days": half_days,
			"missing_punch_days": missing_punch_days,
			"monthly_late_count": getattr(latest_row, "custom_monthly_late_count", 0) if latest_row else 0,
			"monthly_short_hours_count": getattr(latest_row, "custom_monthly_short_hours_count", 0)
			if latest_row
			else 0,
		}

	def _employee_message(self, summary, start_date, end_date):
		lines = [
			_("<p>Weekly attendance summary for {0} to {1}</p>").format(start_date, end_date),
			"<ul>",
		]
		for day in summary["days"]:
			lines.append(
				_(
					"<li>{date}: {status}, Hours: {hours}, Late: {late}, Short Hours: {short_flag}, Missing Punch: {missing}</li>"
				).format(
					date=day["attendance_date"],
					status=day["status"],
					hours=day["working_hours"],
					late=day["late_flag"],
					short_flag=day["short_hours_flag"],
					missing=day["missing_punch_warning"],
				)
			)
		lines.append("</ul>")
		lines.append(
			_(
				"<p>Month to date: Late Count {0}, Short-Hours Grace Count {1}</p>"
			).format(
				summary["totals"]["monthly_late_count"],
				summary["totals"]["monthly_short_hours_count"],
			)
		)
		return "".join(lines)

	def _hr_message(self, summary):
		latest_batch = summary.get("latest_batch") or {}
		return _(
			"""
			<p>Weekly attendance control summary</p>
			<ul>
				<li>Last uploaded till: {last_uploaded_till_date}</li>
				<li>Pending from: {pending_from_date}</li>
				<li>Latest batch: {batch_name} ({batch_status})</li>
				<li>Unresolved corrections: {unresolved_corrections}</li>
				<li>Missing punch cases: {missing_punch_cases}</li>
				<li>Half day conversions: {half_day_conversions}</li>
			</ul>
			"""
		).format(
			last_uploaded_till_date=summary.get("last_uploaded_till_date") or _("Not set"),
			pending_from_date=summary.get("pending_from_date") or _("Not set"),
			batch_name=latest_batch.get("name") or _("None"),
			batch_status=latest_batch.get("processing_status") or _("N/A"),
			unresolved_corrections=summary.get("unresolved_corrections", 0),
			missing_punch_cases=summary.get("missing_punch_cases", 0),
			half_day_conversions=summary.get("half_day_conversions", 0),
		)

	def _manager_message(self, summary, start_date, end_date):
		rows = summary.get("rows", [])
		lines = [
			_("<p>Team attendance summary for {0} to {1}</p>").format(start_date, end_date),
			"<ul>",
		]
		for row in rows[:50]:
			lines.append(
				_("<li>{employee} on {date}: {status}, Hours: {hours}</li>").format(
					employee=row["employee"],
					date=row["attendance_date"],
					status=row["status"],
					hours=row["working_hours"],
				)
			)
		lines.append("</ul>")
		return "".join(lines)

	def _get_employee_map(self, employees):
		if not employees:
			return {}
		fields = ["name", "employee_name"]
		if frappe.db.has_column("Employee", "prefered_email"):
			fields.append("prefered_email")
		if frappe.db.has_column("Employee", "company_email"):
			fields.append("company_email")
		rows = frappe.get_all("Employee", filters={"name": ["in", list(employees)]}, fields=fields)
		return {row.name: row for row in rows}

	def _get_role_emails(self, role):
		user_rows = frappe.get_all(
			"Has Role",
			filters={"role": role},
			fields=["parent"],
			limit_page_length=0,
		)
		emails = []
		for row in user_rows:
			user_email = frappe.db.get_value("User", row.parent, "email")
			if user_email and user_email not in emails:
				emails.append(user_email)
		return emails

	def _get_single_value(self, doctype, fieldname):
		if not frappe.db.exists("DocType", doctype):
			return None
		try:
			return frappe.db.get_single_value(doctype, fieldname)
		except Exception:
			return None
