export function userRoles(user) {
  const roles = Array.isArray(user?.roles)
    ? user.roles
    : String(user?.roles || "").split(/[\s,]+/).filter(Boolean);
  return new Set([...(user?.role ? [user.role] : []), ...roles.map((role) => String(role).toLowerCase())]);
}

export function userIsAdmin(user) {
  const roles = userRoles(user);
  return Boolean(user?.isAdmin || user?.is_admin || roles.has("admin") || roles.has("관리자"));
}

export function userIsCoach(user) {
  const roles = userRoles(user);
  return Boolean(user?.isCoach || user?.is_coach || user?.coachKey || user?.coach_key || roles.has("coach") || roles.has("코치"));
}
