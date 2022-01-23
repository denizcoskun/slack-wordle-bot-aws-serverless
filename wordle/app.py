import logging
import os
from random import random
from shutil import ExecError
from typing import List, Tuple
import boto3
from urllib.parse import parse_qs
import datetime
from game import slack_diff_payload
logger = logging.getLogger()
logger.setLevel(logging.INFO)
from words import WORD_POOL
import random
import json


def get_ddb_connection():
    # ENV = os.environ['Environment']
    # if ENV == 'local':
    #     ddbclient = boto3.client('dynamodb', endpoint_url='http://dynamodb:8000/')
    # else:
    ddbclient = boto3.client('dynamodb')
    return ddbclient

def lambda_handler(event, context):
    res = handle_request(event)
    return {
        "isBase64Encoded": False,
        "statusCode": 200,
        "body": json.dumps(res),
    }

def handle_request(event):
    ddbclient = get_ddb_connection()
    GUESS_TABLE = os.environ.get('GUESS_TABLE', 'WordleGuessTable')
    GAME_TABLE = os.environ.get('GAME_TABLE', 'WordleGameTable')
    raw_body = event['body']
    body = parse_qs(raw_body)
    username = body['user_name'][0]
    guess = body['text'][0]
    date = datetime.date.today().isoformat()
    if not guess or len(guess) != 5 :
        return {"text": "Invalid guess"}
    guess = guess.upper()
    try:
        word, _ = dynamo_get_game(ddbclient, date, GAME_TABLE)
    except Exception as error:
        print('Unable to get a game', error)
        try:
            word = random.choice(WORD_POOL).upper()
            dynamo_create_game(ddbclient, date, word, GAME_TABLE)
        except Exception as err:
            print(err)
            return {"text": "Unable to create a game today"}
    if winner := game_has_winner(date=date, ddbclient=ddbclient, tableName=GAME_TABLE):
        return {"text": f'The game is finished, the winner is <@{winner}>\n>Answer: {word}'}

    existing_guesses = []

    try:
        existing_guesses = get_user_guesses(username, date, ddbclient, GUESS_TABLE)
        if len(existing_guesses) >= 3:
            return {"text": "you have run out of guesses"}
        if guess in existing_guesses:
            return {"text": "you have submitted that guess"}
    except:
        create_user_guess(username, date, guess, ddbclient, GUESS_TABLE)

    existing_guesses.append(guess)
    set_user_guesses(username, date, existing_guesses, ddbclient, GUESS_TABLE)
    if guess == word:
        (successfull, actual_winner) = set_winner(ddbclient, date, username, GAME_TABLE)
        if not successfull:
            return {"text": f'The game is finished, the winner is <@{actual_winner}>\n>Answer: {word}'}
        players = get_players(date, ddbclient, GUESS_TABLE)
        diff = "\n>".join([slack_diff_payload(guess, word, reveal_guess=False) for guess in existing_guesses])
        response = {
            "response_type": "in_channel",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                    "type": "mrkdwn",
                    "text": f'The winner is <@{username}> with *{word}*! :tada: \n>{diff}',
                    },
                },
                {
                "type": "section",
                "text": {
                "type": "mrkdwn",
                "text":
                    f"Today's players ({len(players)}): " +
                    " ".join([f'<@{player}>' for player in players])
                    },
                },
            ],
        }
        return response
    else:
        diff = "\n>".join([slack_diff_payload(guess, word, reveal_guess=True) for guess in existing_guesses])
        if len(existing_guesses) == 3:
            text = f'Sorry, you have run out of guesses. The answer is *{word}*: \n>{diff}'
        else:
            text = f'Your guesses \n>{diff}'
        return {"type": "mrkdwn", "text": text}

def get_user_guesses(username, date, ddbclient, tableName):
    raw = ddbclient.get_item(
            TableName=tableName,
            Key={'username': {'S': username}, 'date': {'S': date}},
            ProjectionExpression="guesses",
        )['Item']['guesses']['L']
    return [g['S'] for g in raw]

def create_user_guess(username, date, guess, ddbclient, tableName):
    ddbclient.put_item(
        TableName=tableName,
        Item={
            'username': {'S': username}, 'date': {'S': date},
            'guesses': {
                "L": [{"S": guess}]
            }
        },
    )
def set_user_guesses(username, date, guesses: List[str], ddbclient, tableName):
    ddbclient.update_item(
        TableName=tableName,
        Key={'username': {'S': username}, 'date': {'S': date}},
        UpdateExpression="SET guesses = :vals",
        ExpressionAttributeValues={
            ":vals": {"L": [{'S': g} for g in guesses]}
        }
    )

def get_players(date, ddbclient, tableName) -> List[str]:
    try:
        raw = ddbclient.scan(
            TableName=tableName,
            FilterExpression="#date = :date",
            ExpressionAttributeValues={
                ":date": {'S': date}
            },
            ExpressionAttributeNames={"#date": "date"},
            ProjectionExpression="username"
        )['Items']
        return [p['username']['S'] for p in raw]
    except Exception as e:
        return []


def dynamo_get_game(ddbclient, date: str, gameTable):
    key = {"date": {"S": date}}
    raw = ddbclient.get_item(
        TableName=gameTable,
        Key=key,
    )['Item']
    winner = None
    if raw.get('winner'):
        winner = raw.get('winner')['S']
    return (raw['word']['S'], winner)

    
def dynamo_create_game(ddbclient, date: str, word: str, tableName):
    ddbclient.put_item(
        TableName=tableName,
        Item={
            "date": {"S": date},
            "word": {"S": word}
        }
    )


def game_has_winner(ddbclient, date: str, tableName) -> str:
    response =  ddbclient.get_item(
        TableName=tableName,
        Key={'date': {'S': date}},
    )
    print(response)
    try:
        return response['Item']['winner']['S']
    except:
        return None

def set_winner(ddbclient, date: str, winner: str, tableName) -> Tuple[bool, str]:
    actual_winner = ddbclient.update_item(
        TableName=tableName,
        Key={'date': {'S': date}},
        UpdateExpression="SET winner = if_not_exists(winner, :winner)",
        ExpressionAttributeValues={
            ":winner": {"S": winner}
        },
        ReturnValues="UPDATED_NEW"
    )['Attributes']['winner']['S']
    return [actual_winner == winner, actual_winner]