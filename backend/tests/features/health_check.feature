Feature: Application Health Check
  As a developer
  I want to verify the application starts correctly
  So that I can be confident the refactor didn't break anything

  Scenario: App imports and is a FastAPI instance
    Given the application is loaded
    Then the app should be a FastAPI instance
    And the health endpoint should respond
