app_name = "snrg_hr"
app_title = "SNRG Human Resources"
app_publisher = "SNRG Electricals"
app_description = "Attendance and payroll control module for SNRG Electricals"
app_email = "admin@snrgelectricals.com"
app_license = "mit"

# Desk workspace and module structure live under the Human Resources module.

after_install = "snrg_hr.setup.after_install"
after_migrate = "snrg_hr.setup.after_migrate"

fixtures = [
	{"dt": "Workspace", "filters": [["name", "=", "Attendance & Payroll Control"]]},
	{"dt": "Report", "filters": [["name", "in", ["Payroll Readiness", "Manager Team Attendance"]]]},
]

# app_include_css = "/assets/snrg_hr/css/snrg_hr.css"
# app_include_js = "/assets/snrg_hr/js/snrg_hr.js"

# doctype_js = {
#     "Attendance": "public/js/attendance.js",
# }

# scheduler_events = {
#     "weekly": [
#         "snrg_hr.tasks.weekly",
#     ],
# }

scheduler_events = {
	"daily": [
		"snrg_hr.tasks.run_daily_maintenance",
	],
}
