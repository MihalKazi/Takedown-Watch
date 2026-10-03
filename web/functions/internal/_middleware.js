/**
 * Cloudflare Pages Function: gates /internal/* behind HTTP Basic Auth.
 *
 * Temporary stand-in for Cloudflare Access (see docs/m1-proposal.md) until Zero Trust is set up.
 * Credentials come from Pages secrets (TW_INTERNAL_USER / TW_INTERNAL_PASS), never committed.
 */
export async function onRequest(context) {
  const { request, env, next } = context;
  const user = env.TW_INTERNAL_USER;
  const pass = env.TW_INTERNAL_PASS;

  if (!user || !pass) {
    return new Response("Internal dashboard is not configured (missing TW_INTERNAL_USER/TW_INTERNAL_PASS).", {
      status: 503,
    });
  }

  const auth = request.headers.get("Authorization") || "";
  const expected = "Basic " + btoa(`${user}:${pass}`);

  if (auth !== expected) {
    return new Response("Authentication required.", {
      status: 401,
      headers: { "WWW-Authenticate": 'Basic realm="Takedown Watch internal", charset="UTF-8"' },
    });
  }

  return next();
}
