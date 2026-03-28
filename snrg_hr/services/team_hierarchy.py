from collections import defaultdict, deque

import frappe


class TeamHierarchyService:
	def get_all_subordinates(self, manager_employee):
		if not manager_employee or not frappe.db.exists("DocType", "Employee"):
			return []

		manager_map = self._build_manager_map()
		seen = set()
		queue = deque([manager_employee])
		subordinates = []

		while queue:
			manager = queue.popleft()
			for employee in manager_map.get(manager, []):
				if employee in seen:
					continue
				seen.add(employee)
				subordinates.append(employee)
				queue.append(employee)

		return subordinates

	def get_manager_for_employee(self, employee):
		if not employee:
			return None

		if frappe.db.has_column("Employee", "custom_reporting_manager_employee"):
			manager = frappe.db.get_value("Employee", employee, "custom_reporting_manager_employee")
			if manager:
				return manager

		if frappe.db.has_column("Employee", "reports_to"):
			return frappe.db.get_value("Employee", employee, "reports_to")

		return None

	def _build_manager_map(self):
		fields = ["name"]
		if frappe.db.has_column("Employee", "custom_reporting_manager_employee"):
			fields.append("custom_reporting_manager_employee")
		if frappe.db.has_column("Employee", "reports_to"):
			fields.append("reports_to")

		rows = frappe.get_all("Employee", fields=fields, limit_page_length=0)
		manager_map = defaultdict(list)
		for row in rows:
			manager = None
			if hasattr(row, "custom_reporting_manager_employee") and row.custom_reporting_manager_employee:
				manager = row.custom_reporting_manager_employee
			elif hasattr(row, "reports_to") and row.reports_to:
				manager = row.reports_to

			if manager:
				manager_map[manager].append(row.name)

		return manager_map
