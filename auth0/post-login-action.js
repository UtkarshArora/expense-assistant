/**
 * Auth0 Post-Login Action: "Add expense claims".
 *
 * Reference copy of the Action deployed in the Auth0 tenant (Actions ->
 * Library, bound to Triggers -> post-login). Editing this file changes
 * nothing until the code is pasted into the dashboard and deployed.
 *
 * Adds namespaced claims to the access token for the Expense Assistant API.
 * backend/app/auth.py reads them (CLAIM_NAMESPACE must match `ns` below).
 *
 * Denies the login outright if the user isn't fully configured, so a user
 * with no role, or a manager/employee missing the data the DB scopes on,
 * never gets a token at all.
 *
 * Inputs (set per user in the dashboard):
 *   - Roles: exactly one of employee | manager | admin
 *   - app_metadata: { "department": "...", "employee_name": "..." }
 *     (app_metadata, not user_metadata: users can edit user_metadata)
 */
exports.onExecutePostLogin = async (event, api) => {
  const ns = "https://expense-assistant/";
  const roles = event.authorization?.roles ?? [];
  // One effective role; the most privileged wins if several are assigned.
  const role = ["admin", "manager", "employee"].find((r) => roles.includes(r));
  const md = event.user.app_metadata ?? {};

  if (!role) return api.access.deny("No role assigned. Ask an admin for access.");
  if (role === "manager" && !md.department)
    return api.access.deny("Manager has no department configured.");
  if (role === "employee" && !md.employee_name)
    return api.access.deny("Employee has no employee_name configured.");

  api.accessToken.setCustomClaim(ns + "role", role);
  api.accessToken.setCustomClaim(ns + "department", md.department ?? null);
  api.accessToken.setCustomClaim(ns + "employee_name", md.employee_name ?? null);
  // Access tokens don't carry these by default; the backend stores them.
  api.accessToken.setCustomClaim(ns + "email", event.user.email ?? null);
  api.accessToken.setCustomClaim(ns + "name", event.user.name ?? null);
};
