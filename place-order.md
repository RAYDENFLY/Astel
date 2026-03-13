# coding: utf-8
import requests
import time
import hashlib
import hmac

host = "https://api.gateio.ws"
prefix = "/api/v4"
headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

url = '/futures/usdt/orders'
query_param = ''
body='{"contract":"BTC_USDT","size":"6024","iceberg":"0","price":"3765","tif":"gtc","text":"t-my-custom-id","stp_act":"-","order_value":"64112.2099000000005","trade_value":"64112.2099000000005","market_order_slip_ratio":"0.03","pos_margin_mode":"isolated"}'
# for `gen_sign` implementation, refer to section `Authentication` above
sign_headers = gen_sign('POST', prefix + url, query_param, body)
headers.update(sign_headers)
r = requests.request('POST', host + prefix + url, headers=headers, data=body)
print(r.json())

Body parameter

{
  "contract": "BTC_USDT",
  "size": "6024",
  "iceberg": "0",
  "price": "3765",
  "tif": "gtc",
  "text": "t-my-custom-id",
  "stp_act": "-",
  "order_value": "64112.2099000000005",
  "trade_value": "64112.2099000000005",
  "market_order_slip_ratio": "0.03",
  "pos_margin_mode": "isolated"
}
Example responses

201 Response

{
  "id": 15675394,
  "user": 100000,
  "contract": "BTC_USDT",
  "create_time": 1546569968,
  "size": "6024",
  "iceberg": "0",
  "left": "6024",
  "price": "3765",
  "fill_price": "0",
  "mkfr": "-0.00025",
  "tkfr": "0.00075",
  "tif": "gtc",
  "refu": 0,
  "is_reduce_only": false,
  "is_close": false,
  "is_liq": false,
  "text": "t-my-custom-id",
  "status": "finished",
  "finish_time": 1514764900,
  "finish_as": "cancelled",
  "stp_id": 0,
  "stp_act": "-",
  "amend_text": "-",
  "order_value": "64112.2099000000005",
  "trade_value": "64112.2099000000005",
  "market_order_slip_ratio": "0.03",
  "pos_margin_mode": "isolated"
}




# coding: utf-8
import requests
import time
import hashlib
import hmac

host = "https://api.gateio.ws"
prefix = "/api/v4"
headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}

url = '/futures/usdt/price_orders'
query_param = ''
body='{"initial":{"contract":"BTC_USDT","size":100,"price":"5.03"},"trigger":{"strategy_type":0,"price_type":0,"price":"3000","rule":1,"expiration":86400},"order_type":"close-long-order"}'
# for `gen_sign` implementation, refer to section `Authentication` above
sign_headers = gen_sign('POST', prefix + url, query_param, body)
headers.update(sign_headers)
r = requests.request('POST', host + prefix + url, headers=headers, data=body)
print(r.json())

Body parameter

{
  "initial": {
    "contract": "BTC_USDT",
    "size": 100,
    "price": "5.03"
  },
  "trigger": {
    "strategy_type": 0,
    "price_type": 0,
    "price": "3000",
    "rule": 1,
    "expiration": 86400
  },
  "order_type": "close-long-order"
}
Example responses

201 Response

{
  "id": 1432329
}
