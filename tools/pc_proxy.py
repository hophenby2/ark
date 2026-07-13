from mitmproxy import ctx, http


TARGET_DOMAIN_SUFFIX = ".hypergryph.com"
LOCAL_SERVER = "127.0.0.1"
LOCAL_PORT = 8443


class Redirector:
    def request(self, flow: http.HTTPFlow) -> None:
        original_host = flow.request.pretty_host
        if not original_host.endswith(TARGET_DOMAIN_SUFFIX):
            return

        original_url = flow.request.url
        flow.request.scheme = "http"
        flow.request.host = LOCAL_SERVER
        flow.request.port = LOCAL_PORT
        flow.request.headers["Host"] = f"{LOCAL_SERVER}:{LOCAL_PORT}"
        flow.request.headers["X-Forwarded-Host"] = original_host
        flow.request.headers["X-Original-URL"] = original_url
        ctx.log.info(f"Redirecting {original_host} to {LOCAL_SERVER}:{LOCAL_PORT}")


addons = [Redirector()]
