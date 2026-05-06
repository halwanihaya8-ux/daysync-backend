import logging
import requests

ZONE_TO_BAND = {
    'optimal': 'HIGH', 'excellent': 'HIGH',
    'normal': 'MEDIUM', 'good': 'MEDIUM', 'fair': 'MEDIUM',
    'fatigued': 'LOW', 'poor': 'LOW',
}

def call_ml_service(data: dict) -> dict:
    try:
        resp = requests.post('http://ml:5001/api/predict', json=data, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        logging.exception('ML fallback used: %s', exc)
        payload = {
            'prediction': data.get('hrv_rmssd_ms', [45])[-1],
            'readiness_zone': 'normal',
            'personal_baseline_hrv': sum(data.get('hrv_rmssd_ms', [45])) / len(data.get('hrv_rmssd_ms', [45])),
            'shap_insight': 'Mock recovery data used because the ML service was unavailable',
        }
    zone = str(payload.get('readiness_zone', 'normal')).lower()
    return {
        'readiness_zone': zone,
        'readiness_band': ZONE_TO_BAND.get(zone, 'MEDIUM'),
        'predicted_hrv': float(payload.get('prediction', 45)),
        'baseline_hrv': float(payload.get('personal_baseline_hrv', 45)),
        'shap_insight': str(payload.get('shap_insight', 'Features are within normal ranges')),
    }
