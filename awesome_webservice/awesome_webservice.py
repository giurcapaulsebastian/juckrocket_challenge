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
db = SQLAlchemy(app, session_options={"expire_on_commit": False})


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
    
    payin_finished = db.Column(db.Boolean, default=False)
    payout_finished = db.Column(db.Boolean, default=False)
    finished = db.Column(db.Boolean, default=False)
    
    def __init__(self, from_iban, to_iban, amount, wallet_id):
        self.from_iban = from_iban
        self.to_iban = to_iban
        self.amount = amount
        self.wallet_id = wallet_id
        super().__init__()


def make_transaction(app, transaction):
    global API_WORKING
    global LAST_CHECKED
    with app.app_context():
        while True:
            while API_WORKING is True:
                events = []
                
                print(f"TRANSACTION!!: {transaction}")
                #try to create wallet or move on
                response = requests.post(url=f"http://127.0.0.1:5000/wallet/{transaction.wallet_id}")
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
                
                
                if not transaction.payin_finished:
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
                        
                    # print(f"Length of events inside thread -> {len(events)}")
                    # print(f"Last checked value -> {LAST_CHECKED}")
                    
                    payin_succeded = False
                    for item in events:
                        if str(item['amount']) == transaction.amount and item['wallet_id'] == transaction.wallet_id:
                            payin_succeded = True
                    if payin_succeded:
                        transaction.payin_finished = True
                        print(f"Transaction wallet({transaction.wallet_id}) : SUCCESFULL PAYIN!")
                    else:
                        print(f"Transaction wallet({transaction.wallet_id}) : FAILED PAYIN!")
                
                if transaction.payin_finished:
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
                    #wait for transaction to finsih by bank api
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
                        
                    # print(f"Length of events inside thread -> {len(events)}")
                    # print(f"Last checked value -> {LAST_CHECKED}")
                    
                    payout_succeded = False
                    for item in events:
                        if str(item['amount']) == transaction.amount and item['wallet_id'] == transaction.wallet_id:
                            payout_succeded = True
                    if payout_succeded:
                        #TRANSACTION FINISHED!
                        transaction.payout_finished = True
                        transaction.finished = True
                        print(f"Transaction wallet({transaction.wallet_id}) : SUCCESFULL PAYOUT!")
                        print(f"Transaction done !")
                        break
                    else:
                        print(f"Transaction wallet({transaction.wallet_id}) : FAILED PAYOUT! Trying again...")
            break

@app.route('/transaction', methods=['POST'])
def initiate_transaction():
    data = request.json
    from_iban, to_iban, amount = data['from_iban'], data['to_iban'], data['amount']
    wallet_id = ''.join(rand.choice(string.ascii_lowercase) for _ in range(8))
    transaction = TransactionModel(from_iban, to_iban, amount, wallet_id)
    db.session.add(transaction)
    t = threading.Thread(target=make_transaction, args=[app, transaction])
    t.daemon = True
    t.start()
    return jsonify(dict(result='Transaction initiated successfully!'))

if __name__ == '__main__':
    app.run(port=5002, debug=True)