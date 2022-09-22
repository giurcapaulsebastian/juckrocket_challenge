#!/usr/bin/env python3
import os, string, threading, time
from collections import deque
from functools import wraps
from secrets import SystemRandom

from flask import Flask, jsonify, request


rand = SystemRandom()
def uniform(a, b):
    return rand.random() * (b - a) + a

# We can assume that a settlement (= transaction) takes at most this long
MAXIMUM_SETTLMENT_DURATION = 60. * 60 * 3 # 3 hours

# Mean time to complete a transaction
MEAN_SETTLEMENT_DURATION = uniform(0.3, 1) * MAXIMUM_SETTLMENT_DURATION
print('Mean settlement duration: {:.2f} hours'.format(MEAN_SETTLEMENT_DURATION / 3600.))

# How much faster time passes, for testing
TIME_FACTOR = 60. * 60  # 1 second simulation time = 60 minutes real time

# What factor of requests will just be silently dropped?
ERROR_RATE = 0.2

# What is the probability that a random request will break the service completely
# for a while?
FAIL_PROBABILITY = 0.02


# "Business logic"
wallets = {}
events = []
event_holes = deque()

def add_event(event):
    if event_holes and (rand.random() < 0.5 or len(event_holes) > 100):
        id = event_holes.popleft()
        # print('old: {}'.format(id))
    else:
        id = len(events) + rand.randint(1, 3)
        for j in range(len(events), id + 1):
            events.append(None)
            if j < id:
                event_holes.append(j)
        assert len(events) == id + 1
        # print('new: {}'.format(id))
    event['created_at'] = time.time()
    event['event_id'] = id
    events[id] = event


def perform_settlement(wallet_id, amount, iban):
    wallets[wallet_id] += amount
    def task():
        delay = uniform(0.5, 1.5) * MEAN_SETTLEMENT_DURATION / TIME_FACTOR
        print('Transaction will take {:.3f} seconds'.format(delay))
        time.sleep(delay)
        print('Transaction wallet({}) += {:d} succeeded'.format(wallet_id, amount))
        add_event(dict(wallet_id=wallet_id, amount=amount))

    t = threading.Thread(target=task)
    t.daemon = True
    t.start()

EVENTS_PER_SECOND = 1
def event_creator():
    i = 0
    while True:
        i += 1
        if i % 10 == 0:
            print('Events: {} ({})'.format(len(events),
                next((i for i in range(len(events)) if events[i] is None), len(events))))
        for _ in range(EVENTS_PER_SECOND):
            wallet_id = ''.join(rand.choice(string.ascii_lowercase) for _ in range(10))
            amount = rand.randint(-1000, 1000)
            add_event(dict(wallet_id=wallet_id, amount=amount))
        time.sleep(1)

t = threading.Thread(target=event_creator)
t.daemon = True
t.start()


# HTTP API
app = Flask(__name__)

def broken():
    raise Exception('everything is broken')


FAIL_UNTIL = 0
def api_function(f):
    @wraps(f)
    def wrapper(*args, **kw):
        global FAIL_UNTIL

        # Are we still broken?
        if time.time() < FAIL_UNTIL:
            # Oops
            FAIL_UNTIL += 60. * 60 / TIME_FACTOR
            print('Failing for one more hour, {:.3f} seconds left'.format(
                FAIL_UNTIL - time.time()))
            broken()

        # If not, should we break now? :)
        if rand.random() < FAIL_PROBABILITY:
            # Fail for 1-24 hours
            FAIL_UNTIL = time.time() + (60. * 60 * uniform(1, 24)) / TIME_FACTOR
            print('Failing for %.3f seconds' % (FAIL_UNTIL - time.time()))
            broken()

        # Or maybe we just want to error out silently for maximum confusion
        if rand.random() < ERROR_RATE:
            print('Failing silently')
            return jsonify(dict(result='success'))
        return f(*args, **kw)
    return wrapper


@app.route('/events/<int:min_id>')
@api_function
def get_events(min_id):
    res = [e for e in events[min_id:] if e is not None]
    return jsonify(dict(result='success', events=res))


@app.route('/wallet/<id>', methods=['POST'])
@api_function
def create_wallet(id):
    if id in wallets:
        return jsonify(dict(result='error'))
    wallets[id] = 0
    return jsonify(dict(result='success'))


@app.route('/settle', methods=['POST'])
@api_function
def settle():
    data = request.json
    amount, wallet_id, type_, iban = data['amount'], data['wallet_id'], data['type'], data['iban']
    assert isinstance(type_, str)
    assert isinstance(wallet_id, str)
    assert isinstance(iban, str)
    assert isinstance(amount, str)
    amount = int(amount)
    if wallet_id in wallets:
        if type_ == 'payin':
            assert amount >= 0
            perform_settlement(wallet_id, amount, iban)
        else:
            assert type_ == 'payout'
            assert 0 <= amount <= wallets[wallet_id]
            perform_settlement(wallet_id, -amount, iban)
    else:
        print('Wallet not found, failing silently')
    return jsonify(dict(result='success'))