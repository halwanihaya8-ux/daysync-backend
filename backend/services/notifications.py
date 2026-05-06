import logging

def send_push(push_token: str | None, message: str) -> bool:
    if not push_token:
        logging.info('Notification skipped: %s', message)
        return False
    logging.info('Notification to %s: %s', push_token, message)
    return True
