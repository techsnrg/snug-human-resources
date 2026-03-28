from frappe.utils import add_days, getdate, nowdate

from snrg_hr.services.attendance_correction_service import AttendanceCorrectionService
from snrg_hr.services.attendance_notification_service import AttendanceNotificationService


def run_daily_maintenance():
	_send_weekly_summaries_if_due()
	_expire_correction_requests()


def _send_weekly_summaries_if_due():
	service = AttendanceNotificationService()
	if not service.should_send_weekly_summary_today():
		return

	end_date = getdate(nowdate())
	start_date = add_days(end_date, -6)
	service.send_weekly_summary(start_date, end_date)


def _expire_correction_requests():
	service = AttendanceCorrectionService()
	service.expire_open_requests()
