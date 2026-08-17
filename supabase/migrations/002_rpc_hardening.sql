-- RPC smú volať len service_role (worker/web server). Anon/authenticated NIKDY —
-- claim_models vracia šifrované sessions a record_usage hýbe kreditom.
revoke execute on function
  claim_models(text, int), heartbeat_models(text), release_models(text),
  release_model(uuid), record_usage(uuid, text, int, int, int, numeric, numeric),
  credit_balance(uuid)
from public, anon, authenticated;

grant execute on function
  claim_models(text, int), heartbeat_models(text), release_models(text),
  release_model(uuid), record_usage(uuid, text, int, int, int, numeric, numeric),
  credit_balance(uuid)
to service_role;

-- SECURITY DEFINER bez pripnutého search_path je klasický footgun.
alter function claim_models(text, int) set search_path = public, pg_temp;
alter function heartbeat_models(text) set search_path = public, pg_temp;
alter function release_models(text) set search_path = public, pg_temp;
alter function release_model(uuid) set search_path = public, pg_temp;
alter function record_usage(uuid, text, int, int, int, numeric, numeric) set search_path = public, pg_temp;
alter function credit_balance(uuid) set search_path = public, pg_temp;
