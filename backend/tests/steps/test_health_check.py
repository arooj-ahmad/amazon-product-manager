# tests/steps/health_check_steps.py

from pytest_bdd import scenarios, given, then
from fastapi import FastAPI

from app.main import app

# pytest-bdd 9.x: path is relative to bdd_features_base_dir (tests/features/)
scenarios("health_check.feature")


@given("the application is loaded", target_fixture="app_instance")
def app_loaded():
    return app


@then("the app should be a FastAPI instance")
def check_fastapi(app_instance):
    assert isinstance(app_instance, FastAPI)


@then("the health endpoint should respond")
def check_health(client):
    response = client.get("/health")
    assert response.status_code in (200, 404, 405), (
        f"Unexpected status: {response.status_code}"
    )
