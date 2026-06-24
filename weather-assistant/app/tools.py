from typing import Any

import requests

WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def geocode_location(location: str) -> dict[str, Any]:
    """Resolves a location name into latitude, longitude, and metadata.

    Args:
        location: The name of the city, region, or address (e.g., "Paris", "San Francisco").

    Returns:
        A dictionary containing coordinates and administrative details:
        - latitude: float
        - longitude: float
        - name: str
        - country: str
        - admin1: str (e.g., state or province)
        - timezone: str
    """
    if not location:
        raise ValueError("Location query cannot be empty.")

    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {"name": location, "count": 1, "language": "en", "format": "json"}

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = data.get("results")
    if not results:
        return {"error": f"Could not find coordinates for location: {location}"}

    res = results[0]
    return {
        "latitude": res.get("latitude"),
        "longitude": res.get("longitude"),
        "name": res.get("name"),
        "country": res.get("country"),
        "admin1": res.get("admin1"),
        "timezone": res.get("timezone", "UTC"),
    }


def get_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetches the current weather and 7-day forecast for the given latitude and longitude.

    Args:
        latitude: The geographic latitude coordinate.
        longitude: The geographic longitude coordinate.

    Returns:
        A dictionary containing current weather conditions and daily highlights.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "auto",
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    current = data.get("current", {})
    daily = data.get("daily", {})

    weather_desc = WMO_WEATHER_CODES.get(
        current.get("weather_code"), "Unknown weather condition"
    )

    # Map daily weather codes to descriptions
    daily_codes = daily.get("weather_code", [])
    daily_desc = [WMO_WEATHER_CODES.get(code, "Unknown") for code in daily_codes]

    return {
        "current": {
            "temperature": current.get("temperature_2m"),
            "apparent_temperature": current.get("apparent_temperature"),
            "humidity": current.get("relative_humidity_2m"),
            "precipitation": current.get("precipitation"),
            "rain": current.get("rain"),
            "showers": current.get("showers"),
            "snowfall": current.get("snowfall"),
            "wind_speed": current.get("wind_speed_10m"),
            "description": weather_desc,
        },
        "daily_forecast": {
            "time": daily.get("time", []),
            "temperature_max": daily.get("temperature_2m_max", []),
            "temperature_min": daily.get("temperature_2m_min", []),
            "precipitation_sum": daily.get("precipitation_sum", []),
            "description": daily_desc,
        },
        "elevation": data.get("elevation"),
        "timezone": data.get("timezone"),
        "timezone_abbreviation": data.get("timezone_abbreviation"),
    }


def get_weather_for_location(location: str) -> dict[str, Any]:
    """Combines geocoding and weather retrieval to fetch weather for a named location.

    Args:
        location: The name of the city, region, or address (e.g., "Paris", "San Francisco").

    Returns:
        A dictionary combining the location details and weather information.
    """
    geo_info = geocode_location(location)
    if "error" in geo_info:
        return geo_info

    lat = geo_info["latitude"]
    lon = geo_info["longitude"]

    weather_info = get_weather(lat, lon)
    return {"location": geo_info, "weather": weather_info}
