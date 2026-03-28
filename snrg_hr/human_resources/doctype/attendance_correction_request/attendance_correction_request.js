frappe.ui.form.on("Attendance Correction Request", {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		if (["Draft", "Rejected"].includes(frm.doc.approval_status)) {
			frm.add_custom_button(__("Submit Request"), () => callAction(frm, "submit_request"));
		}

		if (["Draft", "Submitted"].includes(frm.doc.approval_status)) {
			frm.add_custom_button(__("Approve"), () => promptDecision(frm, "approve_request"));
			frm.add_custom_button(__("Reject"), () => promptDecision(frm, "reject_request"));
		}

		if (frm.doc.approval_status === "Approved" && !frm.doc.reprocessed_flag) {
			frm.add_custom_button(__("Reprocess Attendance"), () => callAction(frm, "reprocess_request"));
		}
	},
});

function callAction(frm, method, args = {}) {
	frappe.call({
		method: `snrg_hr.api.attendance_correction.${method}`,
		args: {
			request_name: frm.doc.name,
			...args,
		},
		freeze: true,
		freeze_message: __("Updating correction request..."),
		callback(r) {
			if (r.message && r.message.message) {
				frappe.show_alert({ message: r.message.message, indicator: "green" });
			}
			frm.reload_doc();
		},
	});
}

function promptDecision(frm, method) {
	frappe.prompt(
		[
			{
				fieldname: "decision_note",
				fieldtype: "Small Text",
				label: __("Decision Note"),
			},
		],
		(values) => callAction(frm, method, values),
		__(method === "approve_request" ? "Approve Request" : "Reject Request"),
		__(method === "approve_request" ? "Approve" : "Reject")
	);
}
