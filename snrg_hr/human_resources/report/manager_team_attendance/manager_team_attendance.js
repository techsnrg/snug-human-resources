frappe.query_reports["Manager Team Attendance"] = {
	filters: [
		{
			fieldname: "manager_employee",
			label: __("Manager Employee"),
			fieldtype: "Link",
			options: "Employee",
		},
		{
			fieldname: "start_date",
			label: __("Start Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.week_start(),
		},
		{
			fieldname: "end_date",
			label: __("End Date"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.week_end(),
		},
	],
};
