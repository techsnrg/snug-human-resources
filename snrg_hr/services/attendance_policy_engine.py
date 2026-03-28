from collections import defaultdict
from datetime import datetime, time, timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, get_time


class AttendancePolicyEngine:
	def __init__(self):
		self.required_hours = 9.0
		self.short_hours_grace_threshold = 8.5
		self.allowed_late_count = 2
		self.allowed_short_hours_count = 2
		self.late_start_time = time(10, 30)
		self.late_cutoff_time = time(11, 0)
		self._load_settings()

	def process_affected_dates(self, affected_dates, batch_name=None):
		results = []
		for employee, dates in affected_dates.items():
			month_groups = defaultdict(list)
			for attendance_date in dates:
				month_groups[(attendance_date.year, attendance_date.month)].append(attendance_date)

			for _month, month_dates in month_groups.items():
				results.extend(
					self._process_employee_month(
						employee=employee,
						month_dates=sorted(month_dates),
						batch_name=batch_name,
					)
				)

		return results

	def _process_employee_month(self, employee, month_dates, batch_name=None):
		first_day = month_dates[0].replace(day=1)
		last_day = month_dates[-1]
		existing_attendance = {
			row.attendance_date: row.name
			for row in frappe.get_all(
				"Attendance",
				filters={
					"employee": employee,
					"attendance_date": ["between", [first_day, last_day]],
				},
				fields=["name", "attendance_date"],
			)
		}

		checkin_rows = frappe.get_all(
			"Employee Checkin",
			filters={
				"employee": employee,
				"time": ["between", [f"{first_day} 00:00:00", f"{last_day} 23:59:59"]],
			},
			fields=["name", "time", "log_type", "device_id"],
			order_by="time asc",
		)

		checkins_by_date = defaultdict(list)
		for row in checkin_rows:
			checkins_by_date[get_datetime(row.time).date()].append(row)

		late_count_used = self._get_existing_monthly_count(
			employee,
			first_day,
			last_day,
			"custom_late_flag",
			exclude_dates=month_dates,
		)
		short_hours_count_used = self._get_existing_monthly_count(
			employee,
			first_day,
			last_day,
			"custom_short_hours_grace_used",
			exclude_dates=month_dates,
		)

		results = []
		for attendance_date in sorted(month_dates):
			checkins = checkins_by_date.get(attendance_date, [])
			if not checkins:
				continue

			evaluation = self._evaluate_day(
				employee=employee,
				attendance_date=attendance_date,
				checkins=checkins,
				late_count_used=late_count_used,
				short_hours_count_used=short_hours_count_used,
			)

			if evaluation["late_flag"]:
				late_count_used += 1
			if evaluation["short_hours_grace_used"]:
				short_hours_count_used += 1

			attendance_name = self._upsert_attendance(
				employee=employee,
				attendance_date=attendance_date,
				existing_attendance_name=existing_attendance.get(attendance_date),
				evaluation=evaluation,
				batch_name=batch_name,
				monthly_late_count=late_count_used,
				monthly_short_hours_count=short_hours_count_used,
			)

			self._log_violations(
				employee=employee,
				attendance_date=attendance_date,
				evaluation=evaluation,
				attendance_name=attendance_name,
				batch_name=batch_name,
			)
			results.append(
				{
					"employee": employee,
					"attendance_date": str(attendance_date),
					"status": evaluation["final_status"],
					"working_hours": evaluation["working_hours"],
				}
			)

		return results

	def _evaluate_day(self, employee, attendance_date, checkins, late_count_used, short_hours_count_used):
		shift_context = self._get_shift_context(employee, attendance_date)
		first_in = get_datetime(checkins[0].time)
		last_out = get_datetime(checkins[-1].time)
		missing_punch_warning = len(checkins) == 1
		if missing_punch_warning:
			last_out = shift_context["assumed_end_datetime"]

		working_hours = max((last_out - first_in).total_seconds() / 3600, 0)
		first_in_time = first_in.time()
		late_minutes = self._minutes_late(first_in_time, shift_context["late_start_time"])
		shortfall_minutes = max(int((self.required_hours - working_hours) * 60), 0)

		final_status = "Present"
		violation_types = []
		late_flag = False
		short_hours_flag = False
		short_hours_grace_used = False

		if first_in_time > self.late_cutoff_time:
			final_status = "Half Day"
			violation_types.append("After 11 AM Half Day")
		elif first_in_time > shift_context["late_start_time"]:
			late_flag = True
			late_occurrence = late_count_used + 1
			if late_occurrence > self.allowed_late_count:
				final_status = "Half Day"
				violation_types.append("Third Late Converted to Half Day")
			else:
				violation_types.append("Late Entry")

		if final_status != "Half Day":
			if working_hours < self.short_hours_grace_threshold:
				final_status = "Half Day"
				short_hours_flag = True
				violation_types.append("Below Minimum Hours")
			elif working_hours < self.required_hours:
				short_hours_flag = True
				short_occurrence = short_hours_count_used + 1
				if short_occurrence > self.allowed_short_hours_count:
					final_status = "Half Day"
					violation_types.append("Short Hours Grace Exhausted")
				else:
					short_hours_grace_used = True
					violation_types.append("Short Hours Grace Used")

		if missing_punch_warning:
			violation_types.append("Missing Punch Assumed Shift End")

		return {
			"employee": employee,
			"attendance_date": attendance_date,
			"first_in_time": first_in,
			"last_out_time": last_out,
			"working_hours": round(working_hours, 2),
			"late_minutes": late_minutes,
			"shortfall_minutes": shortfall_minutes,
			"shift_start": shift_context["shift_start_time"],
			"late_flag": late_flag,
			"short_hours_flag": short_hours_flag,
			"short_hours_grace_used": short_hours_grace_used,
			"missing_punch_warning": missing_punch_warning,
			"violation_types": violation_types,
			"final_status": final_status,
		}

	def _upsert_attendance(
		self,
		employee,
		attendance_date,
		existing_attendance_name,
		evaluation,
		batch_name,
		monthly_late_count,
		monthly_short_hours_count,
	):
		doc = (
			frappe.get_doc("Attendance", existing_attendance_name)
			if existing_attendance_name
			else frappe.new_doc("Attendance")
		)
		doc.employee = employee
		doc.attendance_date = attendance_date
		doc.status = evaluation["final_status"]

		optional_fields = {
			"custom_first_in_time": evaluation["first_in_time"],
			"custom_last_out_time": evaluation["last_out_time"],
			"custom_working_hours": evaluation["working_hours"],
			"custom_late_minutes": evaluation["late_minutes"],
			"custom_shortfall_minutes": evaluation["shortfall_minutes"],
			"custom_monthly_late_count": monthly_late_count,
			"custom_monthly_short_hours_count": monthly_short_hours_count,
			"custom_late_flag": 1 if evaluation["late_flag"] else 0,
			"custom_short_hours_flag": 1 if evaluation["short_hours_flag"] else 0,
			"custom_short_hours_grace_used": 1 if evaluation["short_hours_grace_used"] else 0,
			"custom_missing_punch_warning": 1 if evaluation["missing_punch_warning"] else 0,
			"custom_policy_violation": ", ".join(evaluation["violation_types"]),
			"custom_processed_by_policy_engine": 1,
			"custom_import_batch": batch_name,
		}

		for fieldname, value in optional_fields.items():
			if self._has_field("Attendance", fieldname):
				setattr(doc, fieldname, value)

		doc.save(ignore_permissions=True)
		return doc.name

	def _log_violations(self, employee, attendance_date, evaluation, attendance_name, batch_name):
		if not frappe.db.exists("DocType", "Attendance Violation Log"):
			return

		existing = frappe.get_all(
			"Attendance Violation Log",
			filters={
				"employee": employee,
				"attendance_date": attendance_date,
				"linked_import_batch": batch_name,
			},
			pluck="name",
		)
		for name in existing:
			frappe.delete_doc("Attendance Violation Log", name, ignore_permissions=True, force=1)

		for violation_type in evaluation["violation_types"]:
			doc = frappe.new_doc("Attendance Violation Log")
			doc.employee = employee
			doc.attendance_date = attendance_date
			doc.linked_attendance = attendance_name
			doc.linked_import_batch = batch_name
			doc.first_in_time = evaluation["first_in_time"]
			doc.last_out_time = evaluation["last_out_time"]
			doc.working_hours = evaluation["working_hours"]
			doc.late_minutes = evaluation["late_minutes"]
			doc.shortfall_minutes = evaluation["shortfall_minutes"]
			doc.shift_start = evaluation.get("shift_start")
			doc.violation_type = violation_type
			doc.final_attendance_status = evaluation["final_status"]
			doc.payroll_impact = self._payroll_impact_note(evaluation["final_status"], violation_type)
			doc.insert(ignore_permissions=True)

	def _payroll_impact_note(self, final_status, violation_type):
		if final_status == "Half Day":
			return _("Counts as 0.5 attendance day due to {0}.").format(violation_type)
		return _("No deduction by default; monitor policy usage.")

	def _minutes_late(self, first_in_time, late_start_time):
		if first_in_time <= late_start_time:
			return 0

		start_dt = datetime.combine(datetime.today(), late_start_time)
		first_dt = datetime.combine(datetime.today(), first_in_time)
		return int((first_dt - start_dt).total_seconds() / 60)

	def _get_shift_context(self, employee, attendance_date):
		shift_assignment = self._get_shift_assignment(employee, attendance_date)
		shift_start_time = time(10, 0)
		shift_end_time = time(19, 0)

		if shift_assignment and shift_assignment.get("shift_type"):
			shift_type = frappe.db.get_value(
				"Shift Type",
				shift_assignment["shift_type"],
				["start_time", "end_time"],
				as_dict=True,
			)
			if shift_type:
				shift_start_time = get_time(shift_type.start_time or shift_start_time)
				shift_end_time = get_time(shift_type.end_time or shift_end_time)

		assumed_end_datetime = datetime.combine(attendance_date, shift_end_time)
		if shift_end_time <= shift_start_time:
			assumed_end_datetime = assumed_end_datetime + timedelta(days=1)

		late_start_time = self._apply_time_offset(shift_start_time, minutes=30)
		late_cutoff_time = self._apply_time_offset(shift_start_time, minutes=60)

		return {
			"shift_assignment": shift_assignment,
			"shift_start_time": shift_start_time,
			"shift_end_time": shift_end_time,
			"late_start_time": late_start_time,
			"late_cutoff_time": late_cutoff_time,
			"assumed_end_datetime": assumed_end_datetime,
		}

	def _get_shift_assignment(self, employee, attendance_date):
		if not frappe.db.exists("DocType", "Shift Assignment"):
			return None

		assignments = frappe.get_all(
			"Shift Assignment",
			filters={
				"employee": employee,
				"start_date": ["<=", attendance_date],
				"docstatus": 1,
			},
			fields=["name", "shift_type", "start_date", "end_date"],
			order_by="start_date desc",
		)
		for assignment in assignments:
			if not assignment.end_date or assignment.end_date >= attendance_date:
				return assignment
		return None

	def _apply_time_offset(self, base_time, minutes):
		base_datetime = datetime.combine(datetime.today(), base_time)
		return (base_datetime + timedelta(minutes=minutes)).time()

	def _load_settings(self):
		if not frappe.db.exists("DocType", "Attendance Control Settings"):
			return
		try:
			settings = frappe.get_single("Attendance Control Settings")
		except Exception:
			return

		self.required_hours = settings.get("required_working_hours") or self.required_hours
		grace_minutes = settings.get("short_hours_grace_minutes")
		if grace_minutes:
			self.short_hours_grace_threshold = self.required_hours - (grace_minutes / 60)
		self.allowed_late_count = settings.get("allowed_late_count_per_month") or self.allowed_late_count
		self.allowed_short_hours_count = (
			settings.get("allowed_short_hours_grace_count_per_month")
			or self.allowed_short_hours_count
		)
		self.late_start_time = get_time(settings.get("late_start_time") or self.late_start_time)
		self.late_cutoff_time = get_time(settings.get("late_cutoff_time") or self.late_cutoff_time)

	def _get_existing_monthly_count(self, employee, first_day, last_day, fieldname, exclude_dates):
		if not self._has_field("Attendance", fieldname):
			return 0

		rows = frappe.get_all(
			"Attendance",
			filters={
				"employee": employee,
				"attendance_date": ["between", [first_day, last_day]],
				fieldname: 1,
			},
			fields=["attendance_date"],
		)
		exclude_dates = set(exclude_dates)
		return len([row for row in rows if row.attendance_date not in exclude_dates])

	def _has_field(self, doctype, fieldname):
		try:
			return frappe.db.has_column(doctype, fieldname)
		except Exception:
			return False
