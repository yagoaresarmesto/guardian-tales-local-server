# SPDX-License-Identifier: Apache-2.0
"""Same-origin dashboard controls for services using this save and content pack."""

import json

from ..service_control import NAMES, active_services, service_state


def service_request(handler):
    get = handler.command == "GET" and handler.path == "/api/services"
    stopping = handler.path == "/api/services/stop"
    post = handler.command == "POST" and handler.path in (
        "/api/services/restart",
        "/api/services/stop",
    )
    if not (get or post):
        return False
    db = handler.server.database
    scopes = {"game": db, "inventory": db, "cdn": handler.server.references.directory.parent}
    try:
        # Consume the bounded body before closing, even when rejecting its origin or type.
        raw = handler.read_body(512, "Invalid service request size.") if post else None
        if not handler.allowed_host() or (post and not handler.allowed_origin()):
            handler.json(403, {"error": "Use the dashboard's local address."})
        elif get:
            rows = []
            for kind, label in NAMES.items():
                workers = active_services(kind, scopes[kind])
                if not workers:
                    rows.append(
                        {
                            "id": kind,
                            "label": label,
                            "instance": None,
                            "port": None,
                            "canStop": False,
                            "stopped": False,
                        }
                    )
                for port, instance, marker in workers:
                    state = service_state(marker)
                    rows.append(
                        {
                            "id": kind,
                            "label": label,
                            "instance": instance,
                            "port": port,
                            "canStop": kind == "game" and state == "running",
                            "stopped": state == "stopped",
                        }
                    )
            handler.json(200, {"services": rows})
        elif handler.headers.get_content_type() != "application/json":
            handler.json(415, {"error": "Expected a JSON service request."})
        else:
            body = json.loads(raw)
            if (
                not isinstance(body, dict)
                or set(body) != {"id", "instance"}
                or not isinstance(body["id"], str)
                or body["id"] not in scopes
                or (stopping and body["id"] != "game")
                or not isinstance(body["instance"], str)
            ):
                raise ValueError(
                    "Choose the game backend to stop."
                    if stopping
                    else "Choose a listed backend to restart."
                )
            worker = next(
                (
                    marker
                    for _, token, marker in active_services(body["id"], scopes[body["id"]])
                    if token == body["instance"]
                ),
                None,
            )
            if worker is None:
                handler.json(
                    409, {"error": "The selected backend has already stopped or restarted."}
                )
            elif stopping and service_state(worker) != "running":
                handler.json(
                    409,
                    {
                        "error": "The game backend is already stopped or needs "
                        "to be relaunched once to enable Stop."
                    },
                )
            elif stopping:
                worker.with_suffix(".stop").touch()
                handler.json(202, {"stopping": True})
            else:
                worker.with_suffix(".restart").touch()
                handler.json(202, {"restarting": True})
    except (ValueError, RecursionError) as error:
        handler.json(400, {"error": str(error)})
    except OSError as error:
        handler.json(503, {"error": f"Could not reach a local service: {error}"})
    return True
