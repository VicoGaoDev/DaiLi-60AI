export function isSessionExpiredError(error: any): boolean {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;

  if (status === 401) {
    return true;
  }

  // FastAPI HTTPBearer returns 403 "Not authenticated" when the token
  // is missing, which is the expected stale-session signal in this project.
  return status === 403 && detail === "Not authenticated";
}
