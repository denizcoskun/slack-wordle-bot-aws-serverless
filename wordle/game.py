
from enum import Enum
from typing import List, Tuple
from collections import defaultdict

class Status(Enum):
    match = 0
    partial = 1
    absent = 2

def word_diff(guess: str, word: str):
    word_map =  defaultdict(int)
    word_length = len(guess)
    for idx in range(word_length):
        word_map[word[idx]] += 1
    diff: List[Tuple[str, Status]] = []
    for idx in range(word_length):
        guess_char = guess[idx]
        target_char = word[idx]
        if word_map[guess_char]:
            status = Status.match if guess_char == target_char else Status.partial
            word_map[guess_char] -= 1
            diff.append((guess_char, status))
        else:
            diff.append((guess_char, Status.absent))
    return diff

def slack_diff_payload(guess: str, word: str, reveal_guess: bool) -> str:

    def status_text(char: str,status: Status, with_emoji: bool):
        if status == Status.match:
            return ':large_green_circle:' if with_emoji else f'*{char}*'
        if status == Status.partial:
            return ':large_orange_circle:' if with_emoji else f'{char}'
        return ':white_circle:' if with_emoji else f'{char.lower()}'
    diff = " - ".join(
        [
            "‎".join(
                [
                    status_text(char, status, with_emoji)
                    for (char, status) in word_diff(guess, word) 
                ]
            )
            for with_emoji in ([True, False] if reveal_guess else [True])
        ]
    )
    return diff


class WorldeGame:
    def __init__(self, word: str) -> None:
        self