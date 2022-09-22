from ctypes import sizeof
import json
from secrets import SystemRandom
import threading
from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import os, string, time
import requests

rand = SystemRandom()
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
API_WORKING = True

#Database config and DB models
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir,'db.sqlite')
db = SQLAlchemy(app)


LAST_CHECKED = 0

def event_reader():
    # global events
    global LAST_CHECKED
    global API_WORKING
    time.sleep(3)
    while True:
        while API_WORKING:
            response = requests.get(url=f"http://127.0.0.1:5000/events/{LAST_CHECKED}")
            if response.status_code == 500:
                #application is broken, changed global status
                print('BROKEN!')
                API_WORKING = False
                break
            else:
                try:
                    #this gives keyError if silent fail of get
                    data = response.json()
                    events += data['events']
                    LAST_CHECKED=len(events)
                    print("!!!!EVENTS!!!!")
                    print(f"Length of events inside reader{len(events)}")
                    time.sleep(10)
                except KeyError:
                    #we don nothing and try again
                    time.sleep(10)
                    pass

# t = threading.Thread(target=event_reader)
# t.daemon = True
# t.start()
    
class TransactionModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_iban = db.Column(db.String(30), nullable=False)
    to_iban = db.Column(db.String(30), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    wallet_id = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(10), default="CREATED")
    type = db.Column(db.String(10), default="payin")
    
    def __init__(self, from_iban, to_iban, amount, wallet_id):
        self.from_iban = from_iban
        self.to_iban = to_iban
        self.amount = amount
        self.wallet_id = wallet_id
        super().__init__()


def make_transaction(app,from_iban, to_iban, amount, wallet_id):
    global API_WORKING
    global LAST_CHECKED
    with app.app_context():
        while True:
            while API_WORKING is True:
                events = []
                
                #try to create wallet or move on
                response = requests.post(url=f"http://127.0.0.1:5000/wallet/{wallet_id}")
                if response.status_code == 500:
                    #application is broken, changed global status
                    print('BROKEN!')
                    API_WORKING = False
                    break
                else:
                    data = response.json()
                    if data['result'] == 'error':
                        print("Wallet already exists, moving on...")
                    else:
                        print("Wallet possibly created succesfuly!")
                
                #transaction part
                transaction = TransactionModel(from_iban, to_iban, amount, wallet_id)
                
                #do payin api call
                response = requests.post(url=f"http://127.0.0.1:5000/settle",json={
                    'amount': transaction.amount,
                    'wallet_id': transaction.wallet_id,
                    'type': 'payin',
                    'iban': transaction.to_iban
                })
                if response.status_code == 500:
                    #application is broken, changed global status
                    print('BROKEN!')
                    API_WORKING = False
                    break
                time.sleep(4)
                
                #read events from last_checked index
                response = requests.get(url=f"http://127.0.0.1:5000/events/{LAST_CHECKED}")
                if response.status_code == 500:
                    #application is broken, changed global status
                    print('BROKEN!')
                    API_WORKING = False
                    break
                else:
                    try:
                        #this gives keyError if silent fail of get
                        data = response.json()
                        events = data['events']
                        LAST_CHECKED+=len(events)
                    except KeyError:
                        # silent fail we try again
                        break
                print(f"Length of events inside thread -> {len(events)}")
                print(f"Last checked value -> {LAST_CHECKED}")
                payin_succeded = False
                for item in events:
                    if str(item['amount']) == transaction.amount and item['wallet_id'] == transaction.wallet_id:
                        payin_succeded = True
                if payin_succeded:
                    print(f"Transaction wallet({transaction.wallet_id}) : SUCCESFULL PAYIN!")
                else:
                    print(f"Transaction wallet({transaction.wallet_id}) : FAILED PAYIN!")
                
                response = requests.post(url=f"http://127.0.0.1:5000/settle",json={
                    'amount': transaction.amount,
                    'wallet_id': transaction.wallet_id,
                    'type': 'payout',
                    'iban': transaction.to_iban
                })
                if response.status_code == 500:
                    #application is broken, changed global status
                    print('BROKEN!')
                    API_WORKING = False
                    break
                time.sleep(4)
                
                #read events from last_checked index
                response = requests.get(url=f"http://127.0.0.1:5000/events/{LAST_CHECKED}")
                if response.status_code == 500:
                    #application is broken, changed global status
                    print('BROKEN!')
                    API_WORKING = False
                    break
                else:
                    try:
                        #this gives keyError if silent fail of get
                        data = response.json()
                        events = data['events']
                        LAST_CHECKED+=len(events)
                    except KeyError:
                        # silent fail we try again
                        break
                print(f"Length of events inside thread -> {len(events)}")
                print(f"Last checked value -> {LAST_CHECKED}")
                payin_succeded = False
                for item in events:
                    if str(item['amount']) == transaction.amount and item['wallet_id'] == transaction.wallet_id:
                        payin_succeded = True
                if payin_succeded:
                    print(f"Transaction wallet({transaction.wallet_id}) : SUCCESFULL PAYOUT!")
                else:
                    print(f"Transaction wallet({transaction.wallet_id}) : FAILED PAYOUT!")
                
                # API_WORKING=False
                #wait 3 hours to get the data from the server
                #check payin worked ok
                break
                
                #do payout
                #wait 3 hours to get the settlements data from the server
                #check payout worked ok
            break 
            # time.sleep(1)
            # print("Waiting for API...")

@app.route('/transaction', methods=['POST'])
def initiate_transaction():
    data = request.json
    from_iban, to_iban, amount = data['from_iban'], data['to_iban'], data['amount']
    wallet_id = ''.join(rand.choice(string.ascii_lowercase) for _ in range(8))
    t = threading.Thread(target=make_transaction, args=[app,from_iban, to_iban, amount, wallet_id])
    t.daemon = True
    t.start()
    return jsonify(dict(result='Transaction initiated successfully!'))

if __name__ == '__main__':
    app.run(port=5002, debug=True)