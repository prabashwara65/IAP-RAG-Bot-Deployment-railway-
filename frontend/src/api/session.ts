const TOKEN_KEY = "oiap.access_token";

export function getAccessToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token === null || token.length === 0) {
      window.localStorage.removeItem(TOKEN_KEY);
      return;
    }
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    // Private mode can refuse localStorage; the session then lasts only
    // for this page load via the in-memory copy held by Auth state.
  }
}
