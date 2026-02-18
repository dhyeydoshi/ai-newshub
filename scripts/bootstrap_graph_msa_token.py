import sys
from pathlib import Path

# Allow running this script directly from repo root or from ./scripts.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import msal

from config import settings


def main() -> int:
    client_id = settings.GRAPH_MSA_CLIENT_ID or settings.GRAPH_CLIENT_ID
    authority = settings.GRAPH_MSA_AUTHORITY.rstrip("/")
    reserved_scopes = {"offline_access", "openid", "profile"}
    scopes = [
        scope.strip()
        for scope in settings.GRAPH_MSA_SCOPES
        if scope.strip() and scope.strip().lower() not in reserved_scopes
    ]
    if not scopes:
        scopes = ["https://graph.microsoft.com/Mail.Send"]
    cache_path = Path(settings.GRAPH_MSA_TOKEN_CACHE_FILE)

    if not client_id:
        print("GRAPH_MSA_CLIENT_ID (or GRAPH_CLIENT_ID) is required.", file=sys.stderr)
        return 1

    cache = msal.SerializableTokenCache()
    if cache_path.exists():
        cache.deserialize(cache_path.read_text(encoding="utf-8"))

    app = msal.PublicClientApplication(
        client_id=client_id,
        authority=authority,
        token_cache=cache,
    )

    accounts = app.get_accounts()
    if accounts:
        token_result = app.acquire_token_silent(scopes, account=accounts[0])
        if token_result and token_result.get("access_token"):
            print("Token cache already valid. No action needed.")
            return 0

    flow = app.initiate_device_flow(scopes=scopes)
    message = flow.get("message")
    if not flow.get("user_code") or not message:
        print(f"Unable to start device flow: {flow}", file=sys.stderr)
        return 1

    print(message)
    token_result = app.acquire_token_by_device_flow(flow)
    if not token_result or not token_result.get("access_token"):
        print(f"Device flow failed: {token_result}", file=sys.stderr)
        return 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(cache.serialize(), encoding="utf-8")
    print(f"MSAL delegated token cache saved to {cache_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
