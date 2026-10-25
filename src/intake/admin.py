"""Admin API. Listens on 127.0.0.1 and requires the bearer token from the environment."""

from __future__ import annotations

import secrets

from fastapi import Depends, FastAPI, Header, HTTPException

from intake.store import Database


def create_admin(db: Database, admin_token: str) -> FastAPI:
    app = FastAPI(title="ACE Ops intake admin")

    def require_admin(authorization: str | None = Header(default=None)) -> None:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, admin_token):
            raise HTTPException(status_code=401, detail="Authentication required")

    @app.post("/admin/clients")
    def create_client(_: None = Depends(require_admin)) -> dict[str, str]:
        client_id, invitation_token = db.create_client()
        return {"id": client_id, "invitation_token": invitation_token}

    @app.get("/admin/clients/{client_id}/events")
    def client_events(client_id: str, _: None = Depends(require_admin)) -> list[dict]:
        if not db.client_exists(client_id):
            raise HTTPException(status_code=404, detail="Client not found")
        return db.events_for(client_id)

    @app.get("/admin/clients/{client_id}/answers")
    def client_answers(client_id: str, _: None = Depends(require_admin)) -> list[dict]:
        if not db.client_exists(client_id):
            raise HTTPException(status_code=404, detail="Client not found")
        return db.answers_for(client_id)

    return app
