from frappe.model.document import Document

from snrg_hr.services.attendance_correction_service import AttendanceCorrectionService


class AttendanceCorrectionRequest(Document):
	def validate(self):
		service = AttendanceCorrectionService()
		service.populate_request_context(self)
		service.expire_if_past_deadline(self)
