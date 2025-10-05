import json
import time

import requests
from loguru import logger
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential)

CHAT_COMPLETE_ENDPOINT = "http://chatbot_api:8000/chat/complete"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.Timeout),
)
def send_user_message(query):
    payload = {
        "bot_id": "Meddy",
        "user_id": "user_1",
        "user_message": query,
        "is_sync_request": False,
        "metadata": {"source": "web_app"},
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(
            CHAT_COMPLETE_ENDPOINT, json=payload, headers=headers, timeout=60
        )
        response.raise_for_status()
        return json.loads(response.text)
    except requests.Timeout as e:
        logger.error(f"Request timed out: {e}")
        raise TimeoutError("Request timed out")
    except requests.RequestException as e:
        logger.error(f"Request error occurred: {e}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=20),
    retry=retry_if_exception_type(requests.Timeout),
)
def fetch_bot_response(request_id):
    url = f"{CHAT_COMPLETE_ENDPOINT}/{request_id}"
    try:
        response = requests.get(url=url, timeout=60)
        response.raise_for_status()
        return response.status_code, json.loads(response.text)
    except requests.Timeout as e:
        logger.error(f"Request timed out: {e}")
        raise TimeoutError("Request timed out")
    except requests.RequestException as e:
        logger.error(f"Request error occurred: {e}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.Timeout),
)
def get_chat_complete(query):
    try:
        request_payload = send_user_message(query)
        if request_payload.get("status") == "completed":
            logger.debug(f"Received bot response: {request_payload}")
            return str(request_payload.get("response").get("content"))
        elif request_payload.get("status") == "processing":
            request_id = request_payload.get("task_id")
            status_code, response_payload = fetch_bot_response(request_id)
            if status_code == 200 and response_payload.get("status") == "SUCCESS":
                logger.debug(f"Fetched bot response: {response_payload}")
                return str(response_payload.get("task_result").get("content"))
            else:
                logger.error(f"Error fetching bot response: {response_payload}")
                raise ValueError("Error fetching bot response")
    except Exception as e:
        logger.error(f"Error getting chat completion: {e}")
        raise


def simulate_streaming(text, delay=0.05):
    if not text or not isinstance(text, str):
        return

    words = text.split()
    for i, word in enumerate(words):
        if i == 0:
            yield word
        else:
            yield f" {word}"
        time.sleep(delay)


def streaming_response_generator(query):
    try:
        response_text = get_chat_complete(query)

        yield from simulate_streaming(response_text)

    except Exception as e:
        logger.error(f"Error in streaming response: {e}")
        yield "❌ Đã xảy ra lỗi khi xử lý yêu cầu của bạn."
