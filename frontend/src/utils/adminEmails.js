/**
 * Admin emails from env. Add multiple emails (e.g. personal + business) for dev/admin access.
 * Must match ADMIN_EMAILS on backend. Set in .env:
 *   VITE_ADMIN_EMAILS=feichangfuyou@gmail.com,feichangfuyou@doyou.trade
 */
const ADMIN_EMAILS = (import.meta.env.VITE_ADMIN_EMAILS || "feichangfuyou@gmail.com,feichangfuyou@doyou.trade,feichangfuyou@killswitch.works")
  .split(",")
  .map((e) => e.trim().toLowerCase())
  .filter(Boolean);

export function isAdminEmail(email) {
  return !!email && ADMIN_EMAILS.includes(email.toLowerCase());
}
