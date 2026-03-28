import frappe
from frappe import _
from frappe.utils import now_datetime

from snrg_hr.services.attendance_import_preview import AttendanceImportPreviewService


@frappe.whitelist()
def get_upload_dashboard():
	service = AttendanceImportPreviewService()
	return service.get_dashboard_context()


@frappe.whitelist()
def preview_import(file_url: str):
	if not file_url:
		frappe.throw(_("Please upload a file before previewing."))

	service = AttendanceImportPreviewService()
	return service.preview_file(file_url=file_url)


@frappe.whitelist()
def create_import_batch(file_url: str):
	if not file_url:
		frappe.throw(_("Please upload a file before creating an import batch."))

	service = AttendanceImportPreviewService()
	preview = service.preview_file(file_url=file_url)

	if preview.get("fatal_errors"):
		frappe.throw(_("Resolve preview errors before creating an import batch."))

	batch = frappe.get_doc(
		{
			"doctype": "Attendance Import Batch",
			"uploaded_by": frappe.session.user,
			"uploaded_on": now_datetime(),
			"processing_status": "Validated",
			"source_file_name": preview.get("source_file_name"),
			"source_file": file_url,
			"file_date_from": preview.get("file_date_from"),
			"file_date_to": preview.get("file_date_to"),
			"suggested_pending_from_date": preview.get("pending_from_date"),
			"suggested_pending_to_date": preview.get("suggested_upload_to_date"),
			"last_attendance_covered_till_date": preview.get("last_uploaded_till_date"),
			"next_pending_attendance_from_date": preview.get("pending_from_date"),
			"total_rows": preview.get("total_rows", 0),
			"imported_rows": 0,
			"duplicate_rows": preview.get("duplicate_rows", 0),
			"rejected_rows": preview.get("rejected_rows", 0),
			"unmatched_employee_rows": preview.get("unmatched_employee_rows", 0),
			"invalid_timestamp_rows": preview.get("invalid_timestamp_rows", 0),
			"locked_period_rows": preview.get("locked_period_rows", 0),
			"error_summary": service.build_error_summary(preview),
			"remarks": _("Preview completed. Ready for checkin import and attendance processing."),
		}
	)
	batch.insert()

	return {
		"name": batch.name,
		"processing_status": batch.processing_status,
		"source_file_name": batch.source_file_name,
	}
