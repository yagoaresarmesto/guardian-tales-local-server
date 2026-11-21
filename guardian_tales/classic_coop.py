# SPDX-License-Identifier: Apache-2.0
"""Session-scoped practice for the preserved Fire Co-op Defense stage."""

CREATE = "/escape/request-create"
START = "/escape/start-stage"
END = "/escape/end-stage/v2"
ROUTES = (CREATE, START, END)
STAGE_ID = 303050001
MARKER = "classic_coop_trial.enabled"


class Practice:
    def __init__(self):
        self.created = False
        self.finished = False

    def respond(self, references, route, body):
        if not (references.directory / MARKER).is_file():
            raise ValueError("Classic Co-op practice is disabled")
        if not isinstance(body, dict):
            raise ValueError("Classic Co-op requires a JSON request")
        if route == CREATE:
            if (
                set(body) != {"StageId", "TestMode"}
                or type(body["StageId"]) is not int
                or body["StageId"] != STAGE_ID
                or body["TestMode"] is not True
            ):
                raise ValueError("Classic Co-op supports Fire Defense on Easy in practice mode")
            self.created = True
            self.finished = False
            return {"CoopId": STAGE_ID}
        coop_id = body.get("CoopId")
        if not self.created or type(coop_id) is not int or coop_id != STAGE_ID:
            raise ValueError("Classic Co-op requires a local practice match")
        if route == START:
            if set(body) != {"CoopId"} or self.finished:
                raise ValueError("Invalid Classic Co-op start request")
            return {}
        if route != END or set(body) != {"CoopId", "RaidResult", "Result"}:
            raise ValueError("Invalid Classic Co-op result request")
        self.finished = True
        return {"RewardItems": [], "AddedItems": []}
