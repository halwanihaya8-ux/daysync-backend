import logging
import math
import os
import requests

_cache: dict[str, int] = {}

def get_travel_minutes(origin_lat, origin_lng, dest_lat, dest_lng) -> int:
    key = f'{origin_lat},{origin_lng}->{dest_lat},{dest_lng}'
    if key in _cache:
        return _cache[key]
    api_key = os.getenv('GOOGLE_MAPS_API_KEY')
    if not api_key or None in (origin_lat, origin_lng, dest_lat, dest_lng):
        _cache[key] = 20
        return 20
    try:
        resp = requests.get(
            'https://maps.googleapis.com/maps/api/distancematrix/json',
            params={'origins': f'{origin_lat},{origin_lng}', 'destinations': f'{dest_lat},{dest_lng}', 'mode': 'driving', 'key': api_key},
            timeout=10,
        )
        resp.raise_for_status()
        seconds = resp.json()['rows'][0]['elements'][0]['duration']['value']
        minutes = max(1, math.ceil(seconds / 60))
    except Exception as exc:
        logging.exception('Google Maps fallback used: %s', exc)
        minutes = 20
    _cache[key] = minutes
    return minutes
