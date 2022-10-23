def pluralize(word: str, count: int) -> str:
    return word if count == 1 else f"{word}s"
