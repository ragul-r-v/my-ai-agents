# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

import os
import google.auth
from google.auth.exceptions import DefaultCredentialsError
from dotenv import load_dotenv

# Load local environment variables if available
load_dotenv()

# Determine if we should use Vertex AI or Gemini API (AI Studio)
use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "True").lower() in (
    "true",
    "1",
)

if use_vertex:
    try:
        _, project_id = google.auth.default()
        os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
    except DefaultCredentialsError:
        # Prevent crash if not authenticated yet; user can authenticate or switch to AI Studio API key
        if "GOOGLE_CLOUD_PROJECT" not in os.environ:
            os.environ["GOOGLE_CLOUD_PROJECT"] = "placeholder-project"
    os.environ["GOOGLE_CLOUD_LOCATION"] = os.environ.get(
        "GOOGLE_CLOUD_LOCATION", "global"
    )
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"
else:
    # Explicitly disable Vertex AI to use Google AI Studio API key
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "False"


from .tools import geocode_location, get_weather, get_weather_for_location


root_agent = Agent(
    name="weather_assistant",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Weather Assistant, a helpful AI assistant designed to provide accurate "
        "weather information, short-term forecasts, and smart clothing or activity recommendations "
        "based on the weather.\n\n"
        "Guidelines:\n"
        "1. If the user asks for weather for a specific location, use get_weather_for_location or "
        "geocode_location followed by get_weather.\n"
        "2. Always provide current conditions clearly (temperature, feels-like/apparent temperature, "
        "humidity, wind, and overall description).\n"
        "3. Provide a helpful daily summary or forecast when requested.\n"
        "4. Offer practical advice on clothing (e.g., 'bring an umbrella', 'wear a heavy coat', "
        "or 'sunscreen is recommended') and suitability for outdoor activities based on temperature, "
        "rain/snow, and conditions.\n"
        "5. Never make up/hallucinate weather or coordinate data. If a location is not found, state "
        "that you could not find the location."
    ),
    tools=[geocode_location, get_weather, get_weather_for_location],
)

app = App(
    root_agent=root_agent,
    name="app",
)
