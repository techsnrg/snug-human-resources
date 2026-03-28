frappe.pages["attendance-upload-control"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Attendance Upload Control",
		single_column: true,
	});

	const state = {
		file: null,
		preview: null,
		batch: null,
	};

	page.set_primary_action(__("Preview Import"), () => previewImport(), "search");
	page.add_button(__("Upload File"), () => uploadFile(), "Actions");
	page.add_button(__("Create Import Batch"), () => createImportBatch(), "Actions");
	page.add_button(__("Process Import Batch"), () => processImportBatch(), "Actions");
	page.add_button(__("Refresh Summary"), () => loadDashboard(), "Actions");

	const $body = $(page.body);
	$body.html(`
		<div class="attendance-upload-control">
			<div class="form-message blue">
				Upload an IAS raw punch export, review the preview output, and create a validated import batch.
			</div>
			<div class="row">
				<div class="col-md-4">
					<div class="frappe-card mb-3">
						<div class="frappe-card-head">
							<span class="indicator blue">Control Summary</span>
						</div>
						<div class="frappe-card-body js-dashboard-summary">
							<p>Loading current attendance control state...</p>
						</div>
					</div>
					<div class="frappe-card mb-3">
						<div class="frappe-card-head">
							<span class="indicator green">Selected File</span>
						</div>
						<div class="frappe-card-body js-selected-file">
							<p>No file uploaded yet.</p>
						</div>
					</div>
				</div>
				<div class="col-md-8">
					<div class="frappe-card mb-3">
						<div class="frappe-card-head">
							<span class="indicator orange">Preview Result</span>
						</div>
						<div class="frappe-card-body js-preview-panel">
							<p>Preview details will appear here after a file is uploaded.</p>
						</div>
					</div>
				</div>
			</div>
		</div>
	`);

	const $dashboard = $body.find(".js-dashboard-summary");
	const $selectedFile = $body.find(".js-selected-file");
	const $preview = $body.find(".js-preview-panel");

	function formatValue(value) {
		return value || __("Not set");
	}

	function renderDashboard(data) {
		const lastBatch = data.last_successful_batch;
		$dashboard.html(`
			<p><strong>Last attendance uploaded till:</strong> ${formatValue(data.last_uploaded_till_date)}</p>
			<p><strong>Attendance pending from:</strong> ${formatValue(data.pending_from_date)}</p>
			<p><strong>Weekly upload day:</strong> ${formatValue(data.weekly_upload_day)}</p>
			<p><strong>Pending upload alert days:</strong> ${formatValue(data.pending_upload_alert_days)}</p>
			<p><strong>Unresolved corrections:</strong> ${data.unresolved_corrections || 0}</p>
			<p><strong>Unprocessed batches:</strong> ${data.unprocessed_batches || 0}</p>
			<p><strong>Last successful batch:</strong> ${lastBatch ? frappe.utils.escape_html(lastBatch.name) : __("None")}</p>
		`);
	}

	function renderSelectedFile() {
		if (!state.file) {
			$selectedFile.html("<p>No file uploaded yet.</p>");
			return;
		}

		$selectedFile.html(`
			<p><strong>File name:</strong> ${frappe.utils.escape_html(state.file.file_name || "")}</p>
			<p><strong>File URL:</strong> ${frappe.utils.escape_html(state.file.file_url || "")}</p>
			<p><strong>Import batch:</strong> ${state.batch ? frappe.utils.escape_html(state.batch.name || "") : __("Not created yet")}</p>
		`);
	}

	function renderPreview(data) {
		const warningHtml = (data.warnings || [])
			.map((item) => `<li>${frappe.utils.escape_html(item)}</li>`)
			.join("");
		const fatalHtml = (data.fatal_errors || [])
			.map((item) => `<li>${frappe.utils.escape_html(item)}</li>`)
			.join("");
		const unmatchedHtml = (data.unmatched_employee_codes || [])
			.slice(0, 10)
			.map((item) => `<li>${frappe.utils.escape_html(item)}</li>`)
			.join("");
		const sampleHtml = (data.sample_rows || [])
			.map(
				(row) => `
					<tr>
						<td>${row.row_number}</td>
						<td>${frappe.utils.escape_html(row.biometric_employee_code || "")}</td>
						<td>${frappe.utils.escape_html(row.punch_timestamp || "")}</td>
						<td>${frappe.utils.escape_html(row.direction || "")}</td>
						<td>${frappe.utils.escape_html(row.device_id || "")}</td>
					</tr>
				`
			)
			.join("");

		$preview.html(`
			<div class="row mb-3">
				<div class="col-md-6">
					<p><strong>File date range:</strong> ${formatValue(data.file_date_from)} to ${formatValue(data.file_date_to)}</p>
					<p><strong>Total rows:</strong> ${data.total_rows || 0}</p>
					<p><strong>Imported rows candidate:</strong> ${data.imported_rows || 0}</p>
					<p><strong>Rejected rows:</strong> ${data.rejected_rows || 0}</p>
				</div>
				<div class="col-md-6">
					<p><strong>Duplicate rows:</strong> ${data.duplicate_rows || 0}</p>
					<p><strong>Unmatched employee rows:</strong> ${data.unmatched_employee_rows || 0}</p>
					<p><strong>Invalid timestamp rows:</strong> ${data.invalid_timestamp_rows || 0}</p>
					<p><strong>Locked period rows:</strong> ${data.locked_period_rows || 0}</p>
				</div>
			</div>
			<p><strong>Suggested upload range:</strong> ${formatValue(data.pending_from_date)} to ${formatValue(data.suggested_upload_to_date)}</p>
			${fatalHtml ? `<div class="form-message red"><strong>Preview errors</strong><ul>${fatalHtml}</ul></div>` : ""}
			${warningHtml ? `<div class="form-message orange"><strong>Warnings</strong><ul>${warningHtml}</ul></div>` : ""}
			${unmatchedHtml ? `<div><strong>Unmatched employee codes</strong><ul>${unmatchedHtml}</ul></div>` : ""}
			<div class="mt-3">
				<strong>Sample rows</strong>
				<table class="table table-bordered table-sm mt-2">
					<thead>
						<tr>
							<th>Row</th>
							<th>Employee Code</th>
							<th>Punch Timestamp</th>
							<th>Direction</th>
							<th>Device ID</th>
						</tr>
					</thead>
					<tbody>
						${sampleHtml || '<tr><td colspan="5">No sample rows available</td></tr>'}
					</tbody>
				</table>
			</div>
		`);
	}

	function loadDashboard() {
		frappe.call({
			method: "snrg_hr.api.attendance_upload.get_upload_dashboard",
			callback(r) {
				renderDashboard(r.message || {});
			},
		});
	}

	function uploadFile() {
		new frappe.ui.FileUploader({
			folder: "Home/Attachments",
			restrictions: {
				allowed_file_types: [".csv", ".xlsx"],
			},
			on_success(fileDoc) {
				state.file = fileDoc;
				state.preview = null;
				state.batch = null;
				renderSelectedFile();
				$preview.html("<p>File uploaded. Click <strong>Preview Import</strong> to validate it.</p>");
			},
		});
	}

	function previewImport() {
		if (!state.file || !state.file.file_url) {
			frappe.msgprint(__("Upload a CSV or XLSX file first."));
			return;
		}

		frappe.call({
			method: "snrg_hr.api.attendance_upload.preview_import",
			args: {
				file_url: state.file.file_url,
			},
			freeze: true,
			freeze_message: __("Previewing attendance file..."),
			callback(r) {
				state.preview = r.message || {};
				renderPreview(state.preview);
			},
		});
	}

	function createImportBatch() {
		if (!state.file || !state.file.file_url) {
			frappe.msgprint(__("Upload and preview a file before creating an import batch."));
			return;
		}

		frappe.call({
			method: "snrg_hr.api.attendance_upload.create_import_batch",
			args: {
				file_url: state.file.file_url,
			},
			freeze: true,
			freeze_message: __("Creating attendance import batch..."),
			callback(r) {
				state.batch = r.message || null;
				renderSelectedFile();
				if (state.batch && state.batch.name) {
					frappe.show_alert({
						message: __("Import batch {0} created", [state.batch.name]),
						indicator: "green",
					});
					loadDashboard();
				}
			},
		});
	}

	function processImportBatch() {
		if (!state.batch || !state.batch.name) {
			frappe.msgprint(__("Create an import batch before processing."));
			return;
		}

		frappe.call({
			method: "snrg_hr.api.attendance_upload.process_import_batch",
			args: {
				batch_name: state.batch.name,
			},
			freeze: true,
			freeze_message: __("Creating employee checkins and recalculating attendance..."),
			callback(r) {
				const result = r.message || {};
				frappe.show_alert({
					message: __(
						"Processed batch {0}: {1} checkins created, {2} rows skipped",
						[result.batch_name, result.created_checkins || 0, result.skipped_rows || 0]
					),
					indicator: "green",
				});
				loadDashboard();
			},
		});
	}

	loadDashboard();
	renderSelectedFile();
};
