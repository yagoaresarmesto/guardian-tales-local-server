# SPDX-License-Identifier: Apache-2.0
"""Local KongPub configuration and locally issued single-guest credentials."""

PLATFORM_ROUTES = ("/app-info", "/game/maintenance", "/kong/sign-in", "/kong/sign-up")


def dispatch(route, body, api_port, asset_port=18080, guest_store=None):
    if not isinstance(body, dict):
        return 400, {"Error": "LOCAL_INVALID_REQUEST"}
    if route not in PLATFORM_ROUTES:
        return 503, {"Error": "LOCAL_PLATFORM_NOT_IMPLEMENTED"}
    if route in ("/kong/sign-in", "/kong/sign-up"):
        if (
            not guest_store
            or not isinstance(body.get("AuthKind"), str)
            or not isinstance(body.get("Token"), str)
        ):
            return 400, {"Error": "LOCAL_INVALID_REQUEST"}
        return 200, {"Body": guest_store.platform_credentials()}
    if body.get("Version") != "v3.57.0" or body.get("Market") != "googleplay":
        return 400, {"Error": "LOCAL_UNSUPPORTED_CLIENT"}
    if route == "/game/maintenance":
        if body.get("AppId") != "422316":
            return 400, {"Error": "LOCAL_UNSUPPORTED_APP"}
        return 200, {"Body": {"UpdateRequired": False}}
    info = body.get("SystemInfo")
    if not isinstance(info, dict) or info.get("AppId") != "422316":
        return 400, {"Error": "LOCAL_UNSUPPORTED_APP"}
    # These names/types were verified in a public 3.57.0 response and the
    # already-parsed client AppInfo. URLs now refer only to the local instance.
    local_web = "http://127.0.0.1:17657/local-info"
    app = {
        name: local_web
        for name in (
            "csUrl",
            "faqUrl",
            "webUrl",
            "noticeUrl",
            "summonProbUrl",
            "summonItemProbUrl",
            "openSourceLicenseUrl",
            "turntableEventProbUrl",
        )
    }
    app.update(
        TermsPath="media/terms/global/en/service_policies_enUS.txt",
        CdnAddress="http://127.0.0.1:" + str(asset_port) + "/live/global/0491",
        fundActPath="media/terms/console/payment_service_enUS.txt",
        ServerAddress="127.0.0.1:" + str(api_port),
        UsePrevWebView="1",
        PrivacyPolicyPath="media/terms/global/en/personal_info_enUS.txt",
        commercialActPath="media/terms/console/electronic_transactions_enUS.txt",
        ForceUpdateVersion="v3.57.0",
        InReview=False,
        UpdateRequired=False,
    )
    return 200, {
        "Body": {
            "AppInfoData": app,
            "WhiteListed": False,
            "InReview": False,
            "UpdateRequired": False,
        }
    }
