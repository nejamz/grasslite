import asyncio
import random
import time
import uuid
import json
from curl_cffi import requests
import base64
from loguru import logger
from fake_useragent import UserAgent
from base64 import b64decode, b64encode
import websockets
from websockets_proxy import Proxy, proxy_connect

def get_ip_token(deviceid, userid, rdmua, proxy=None):
    try:
        url = f"https://director.getgrass.io/checkin"
        headers = {
            "content-type": "application/json",
            "origin": "chrome-extension://ilehaonighjijnmpnagapkhpcdbhclfg",
            "user-agent": rdmua
        }

        data = {
            "browserId": deviceid,
            "userId": userid,
            "version": "5.1.1",
            "extensionId": "ilehaonighjijnmpnagapkhpcdbhclfg",
            "userAgent": rdmua,
            "deviceType": "extension"
        }

        # Proxy configuration (if provided)
        proxies = None
        if proxy:
            proxies = {
                "http": proxy,
                "https": proxy
            }

        # Sending the POST request through the proxy (if any)
        response = requests.post(url, headers=headers, json=data, proxies=proxies)
        response_data = response.json()

        # Extract the IP and token
        destinations = response_data.get("destinations", [])
        token = response_data.get("token", "")

        if destinations and token:
            ip = destinations[0]  # Assuming the first destination IP is used
            ws_url = f"ws://{ip}:80/?token={token}"
            return ws_url
        else:
            return "Error: Destinations or token missing."

    except Exception as e:
        return str(e)
    
def http_req(uid, url, rdmua, proxy=None):
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": rdmua
    }

    # Proxy configuration (if provided)
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy
        }

    try:
        # Sending the GET request
        response = requests.get(url, headers=headers, proxies=proxies)
        
        # Checking for a successful response
        result = response.json()
        content = response.text
        code = result.get('code')
        
        if code is None:
            logger.error("Error sending HTTP request")
            logger.error(f"Status: {response.status_code}")
        else:
            logger.info(f"HTTP request success: {code}")
            logger.info(f"Status: {response.status_code}")
            
            # Encoding the response body to base64
            response_body = base64.b64encode(content.encode()).decode()
            
            return {
                "id": uid,  # Assuming you have message_auth["id"]
                "origin_action": "HTTP_REQUEST",
                "result": {
                    "url": url,  # Assuming you want to return the URL
                    "status": response.status_code,
                    "status_text": response.reason,
                    "headers": dict(response.headers),
                    "body": response_body
                }
            }

    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP request failed: {e}")
        return None
    
# Function to connect to WebSocket using HTTP proxy with websockets library
async def connect_to_ws(http_proxy, user_id):
    user_agent = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36"
    ]
    random_user_agent = random.choice(user_agent)
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, http_proxy))
    logger.info(f"Device ID: {device_id}")

    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            custom_headers = {
                "user-agent": random_user_agent,
                "origin": "chrome-extension://ilehaonighjijnmpnagapkhpcdbhclfg"
            }

            # Get WebSocket URI from get_ip_token function (using ws://)
            uri = get_ip_token(device_id, user_id, custom_headers["user-agent"], http_proxy)

            # Start tracking connection time
            start_time = time.time()

            # Create WebSocket connection using websockets library
            #async with websockets.connect(uri, additional_headers=custom_headers) as websocket:
            proxy = Proxy.from_url(http_proxy)
            async with proxy_connect(uri, proxy=proxy,
                                     extra_headers=custom_headers) as websocket:
                connection_time = time.time() - start_time
                logger.info(f"WebSocket connected in {connection_time:.2f} seconds")

                # Receive initial response
                response = await websocket.recv()
                message_auth = json.loads(response)
                logger.info(f"Received message: {message_auth}")

                # Handle HTTP_REQUEST action
                if message_auth["action"] == "HTTP_REQUEST":
                    httpreq_response = http_req(message_auth["id"], message_auth["data"]["url"], custom_headers['user-agent'], http_proxy)
                    logger.debug(f"HTTP Request Response: {httpreq_response}")
                    await websocket.send(json.dumps(httpreq_response))
                
                    while True:
                        send_ping = {
                            "id": str(uuid.uuid4()),
                            "version": "1.0.0",
                            "action": "PING",
                            "data": {}
                        }
                        logger.debug(f"Send ping: {send_ping}")
                        await websocket.send(json.dumps(send_ping))

                        response_ping = await websocket.recv()
                        message_ping = json.loads(response_ping)
                        logger.info(f"Received ping response: {message_ping}")

                        if message_ping["action"] == "PONG":
                            pong_response = {
                                "id": message_ping["id"],
                                "origin_action": "PONG"
                            }
                            logger.debug(f"Send pong: {pong_response}")
                            await websocket.send(json.dumps(pong_response))
        except Exception as e:
            logger.error(f"Error: {e}")

# Main function for reading proxies and starting connections
async def main():
    _user_id = input('Please Enter your user ID: ')
    with open('local_proxies.txt', 'r') as file:
        local_proxies = file.read().splitlines()
    tasks = [asyncio.ensure_future(connect_to_ws(i, _user_id)) for i in local_proxies]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    asyncio.run(main())